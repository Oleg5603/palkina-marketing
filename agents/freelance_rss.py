"""
Парсер фриланс-бирж через RSS.
Ищет заказы на сайты, генерирует отклик через GigaChat,
отправляет уведомление в Telegram.

Запуск:
  python freelance_rss.py
  python freelance_rss.py --dry-run   — без отправки в Telegram
"""

import argparse
import asyncio
import hashlib
import io
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import feedparser
import httpx
from dotenv import dotenv_values

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"
_SEEN = _ROOT / "freelance_seen.json"

_env = dotenv_values(_ENV)
TELEGRAM_TOKEN       = _env.get("TELEGRAM_TOKEN", "")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")

# Ваш личный Telegram chat_id — куда слать уведомления
OWNER_CHAT_ID = _env.get("OWNER_CHAT_ID", "")

_GC_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API  = "https://gigachat.devices.sberbank.ru/api/v1"
_TG_API  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("freelance_rss")

# ─── RSS-ленты ───────────────────────────────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "Хабр Фриланс",
        "url":  "https://freelance.habr.com/tasks.rss",
    },
    {
        "name": "Kwork — Заказы",
        "url":  "https://kwork.ru/rss/projects/cat/1",  # категория «Сайты»
    },
    {
        "name": "FL.ru",
        "url":  "https://www.fl.ru/rss/all.xml",
    },
]

# ─── Ключевые слова ─────────────────────────────────────────────────────────
KEYWORDS = [
    "разработка сайта", "создание сайта", "сделать сайт", "нужен сайт",
    "лендинг", "landing page", "одностраничник",
    "верстка", "вёрстка", "сверстать",
    "wordpress", "битрикс", "elementor",
    "интернет-магазин", "корпоративный сайт",
    "веб-сайт", "веб сайт",
    "доработка сайта", "правки сайта", "доработать сайт",
    "front-end", "frontend", "html css",
]

NEGATIVE_KEYWORDS = [
    "голосован", "луков", "отзыв", "скрипт для", "парсинг",
    "база данных", "базу продавц", "seo продвижен", "реклам",
    "копирайт", "тексты", "написать тексты", "контент",
]

# ─── Системный промпт для отклика ────────────────────────────────────────────
_SYSTEM = """Ты — веб-разработчик, отвечаешь на заказ фрилансера.
Напиши короткий отклик (3–4 предложения):
- Первое: покажи что понял задачу, упомяни конкретику из заказа
- Второе: коротко о своём опыте (делаю сайты под ключ, нутрициологи, психологи, бизнес)
- Третье: конкретное предложение (сроки, подход)
- Без цены в тексте. Тёплый профессиональный тон. Без шаблонных фраз типа "готов помочь"."""


def load_seen() -> set:
    if not _SEEN.exists():
        return set()
    return set(json.loads(_SEEN.read_text(encoding="utf-8-sig")))


def save_seen(seen: set) -> None:
    _SEEN.write_text(json.dumps(list(seen), ensure_ascii=False), encoding="utf-8")


def entry_id(entry) -> str:
    raw = getattr(entry, "id", "") or getattr(entry, "link", "") or entry.get("title", "")
    return hashlib.md5(raw.encode()).hexdigest()


def has_keyword(text: str) -> bool:
    t = text.lower()
    if any(neg in t for neg in NEGATIVE_KEYWORDS):
        return False
    return any(kw in t for kw in KEYWORDS)


def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def fetch_feed(feed: dict) -> list[dict]:
    try:
        parsed = feedparser.parse(feed["url"])
        results = []
        for entry in parsed.entries:
            title   = clean_html(getattr(entry, "title", ""))
            summary = clean_html(getattr(entry, "summary", ""))
            link    = getattr(entry, "link", "")
            full    = f"{title} {summary}"
            if has_keyword(full):
                results.append({
                    "source":  feed["name"],
                    "title":   title,
                    "summary": summary[:300],
                    "link":    link,
                    "id":      entry_id(entry),
                })
        log.info("%s: найдено %d подходящих из %d", feed["name"], len(results), len(parsed.entries))
        return results
    except Exception as e:
        log.warning("Ошибка RSS %s: %s", feed["name"], e)
        return []


async def gigachat_token() -> str | None:
    if not GIGACHAT_CREDENTIALS:
        return None
    try:
        async with httpx.AsyncClient(verify=False, timeout=15, trust_env=False) as client:
            r = await client.post(
                _GC_AUTH,
                headers={
                    "Authorization": f"Basic {GIGACHAT_CREDENTIALS}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": "GIGACHAT_API_PERS"},
            )
            r.raise_for_status()
            return r.json()["access_token"]
    except Exception as e:
        log.error("GigaChat token: %s", e)
        return None


async def generate_reply(gc_token: str, order: dict) -> str | None:
    prompt = f'Заказ: {order["title"]}\n\nОписание: {order["summary"]}'
    try:
        async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as client:
            r = await client.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens": 250,
                    "temperature": 0.7,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error("GigaChat generate: %s", e)
        return None


async def send_telegram(order: dict, reply: str) -> None:
    if not TELEGRAM_TOKEN or not OWNER_CHAT_ID:
        log.warning("TELEGRAM_TOKEN или OWNER_CHAT_ID не заданы")
        return
    text = (
        f"🆕 Новый заказ — {order['source']}\n\n"
        f"{order['title']}\n"
        f"{order['summary']}\n\n"
        f"🔗 {order['link']}\n\n"
        f"───────────────\n"
        f"💬 Готовый отклик:\n{reply}"
    )
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            await client.post(f"{_TG_API}/sendMessage", json={
                "chat_id": OWNER_CHAT_ID,
                "text":    text,
            })
        log.info("Отправлено в Telegram: %s", order["title"][:50])
    except Exception as e:
        log.error("Telegram send: %s", e)


async def run(dry_run: bool, limit: int = 0) -> None:
    seen = load_seen()
    all_orders = []

    for feed in RSS_FEEDS:
        orders = fetch_feed(feed)
        all_orders.extend(orders)
        time.sleep(1)

    new_orders = [o for o in all_orders if o["id"] not in seen]
    log.info("Новых заказов: %d", len(new_orders))

    if not new_orders:
        return

    gc_token = await gigachat_token()

    if limit:
        new_orders = new_orders[:limit]

    for order in new_orders:
        print(f"\n{'─'*50}")
        print(f"[{order['source']}] {order['title']}")
        print(f"URL: {order['link']}")
        print(f"Описание: {order['summary'][:150]}...")

        reply = None
        if gc_token:
            reply = await generate_reply(gc_token, order)
            if reply:
                print(f"\nОТКЛИК:\n{reply}")

        if not dry_run and reply:
            await send_telegram(order, reply)

        seen.add(order["id"])
        save_seen(seen)
        await asyncio.sleep(1)

    log.info("Готово. Обработано: %d заказов", len(new_orders))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять в Telegram")
    parser.add_argument("--limit", type=int, default=0, help="Сколько заказов за раз (0 = все)")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, args.limit))
