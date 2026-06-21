"""
Поиск заказов на сайты в VK через newsfeed.search.
Генерирует отклик через GigaChat, отправляет в Telegram.

Запуск:
  python vk_order_scout.py
  python vk_order_scout.py --dry-run
  python vk_order_scout.py --limit 3
"""

import argparse
import asyncio
import hashlib
import io
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import dotenv_values

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"
_SEEN = _ROOT / "vk_orders_seen.json"

_env = dotenv_values(_ENV)
VK_USER_TOKEN        = _env.get("VK_USER_TOKEN", "")
TELEGRAM_TOKEN       = _env.get("TELEGRAM_TOKEN", "")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")
OWNER_CHAT_ID        = _env.get("OWNER_CHAT_ID", "")

_VK_API  = "https://api.vk.com/method"
_VK_VER  = "5.199"
_GC_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API  = "https://gigachat.devices.sberbank.ru/api/v1"
_TG_API  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

MAX_POST_AGE_DAYS = 3
MIN_TEXT_LEN = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("vk_order_scout")

SEARCH_QUERIES = [
    "нужен разработчик сайта",
    "ищу разработчика сайта",
    "кто делает сайты",
    "заказать лендинг",
    "нужен верстальщик",
    "нужен фрилансер сайт",
    "помогите с сайтом",
    "посоветуйте разработчика",
]

# Обязательно присутствие хотя бы одного — явный найм
HIRE_INTENT = [
    "нужен разработчик", "ищу разработчика", "кто делает сайт",
    "кто может сделать", "посоветуйте разработчика", "заказать сайт",
    "заказать лендинг", "нужен верстальщик", "ищу верстальщика",
    "помогите с сайтом", "кто возьмётся", "кто возьмется",
    "нужна помощь с сайтом", "ищу исполнителя", "нужен фрилансер",
]

# Достаточно одного из этих — тема веб-разработки
TOPIC_KEYWORDS = [
    "сайт", "лендинг", "landing", "верстка", "wordpress",
    "битрикс", "интернет-магазин", "веб-разработка",
]

NEGATIVE_KEYWORDS = [
    # сам делает — не нанимает
    "работаю над", "делаю сам", "создаю сам", "пробую создать",
    "решила сделать", "решил сделать", "сам разобрался", "сама разобралась",
    "учусь делать", "попробовала создать", "попробовал создать",
    # продают, не покупают
    "продам сайт", "продаю сайт", "готовый сайт", "купить сайт",
    "зарабатывай", "заработок на сайте", "вакансия", "требуется сотрудник",
    "ищу работу", "ищу клиентов", "предлагаю услуги",
    # спам без реального заказа
    "размещено на сайте", "shikari.do", "getclient.xyz",
    "freelancehunt", "fl.ru/projects", "utm_campaign",
]

_SYSTEM = """Ты — веб-разработчик. Пишешь короткий отклик на пост ВКонтакте, где человек ищет разработчика сайта.

Правила:
- 3 предложения максимум
- Первое: покажи что понял конкретную задачу из поста
- Второе: коротко об опыте (сайты под ключ, нутрициологи, психологи, малый бизнес)
- Третье: конкретное предложение с примерными сроками
- Тон: живой, не шаблонный, без "рад помочь" и "готов рассмотреть"
- Без цены в тексте"""


def load_seen() -> set:
    if not _SEEN.exists():
        return set()
    try:
        return set(json.loads(_SEEN.read_text(encoding="utf-8-sig")))
    except Exception:
        return set()


def save_seen(seen: set) -> None:
    _SEEN.write_text(json.dumps(list(seen), ensure_ascii=False), encoding="utf-8")


def post_key(item: dict) -> str:
    raw = f"{item.get('owner_id')}_{item.get('id')}"
    return hashlib.md5(raw.encode()).hexdigest()


def is_relevant(text: str) -> bool:
    t = text.lower()
    if any(neg in t for neg in NEGATIVE_KEYWORDS):
        return False
    # Оба условия: явное намерение нанять + тема веб-разработки
    has_intent = any(kw in t for kw in HIRE_INTENT)
    has_topic  = any(kw in t for kw in TOPIC_KEYWORDS)
    return has_intent and has_topic


def search_posts(query: str, count: int = 20) -> list[dict]:
    try:
        r = httpx.get(f"{_VK_API}/newsfeed.search", params={
            "access_token": VK_USER_TOKEN,
            "q":            query,
            "count":        count,
            "v":            _VK_VER,
        }, timeout=15, trust_env=False)
        data = r.json()
        if "error" in data:
            log.warning("newsfeed.search '%s': %s", query, data["error"]["error_msg"])
            return []
        return data["response"].get("items", [])
    except Exception as e:
        log.warning("newsfeed.search ошибка: %s", e)
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


async def generate_reply(gc_token: str, text: str) -> str | None:
    try:
        async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as client:
            r = await client.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": f"Пост: {text[:400]}"},
                    ],
                    "max_tokens": 220,
                    "temperature": 0.7,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.error("GigaChat generate: %s", e)
        return None


async def send_telegram(item: dict, reply: str) -> None:
    if not TELEGRAM_TOKEN or not OWNER_CHAT_ID:
        return
    owner_id = item.get("owner_id", 0)
    post_id  = item.get("id", 0)
    vk_link  = f"https://vk.com/wall{owner_id}_{post_id}"
    text_raw = item.get("text", "")[:250]

    is_aggregator = "t.me/" in item.get("text", "")
    source_label  = "📢 Через агрегатор (нажмите t.me/ ссылку в посте)" if is_aggregator else "👤 Прямой пост"
    msg = (
        f"🔍 Заказ из VK — {source_label}\n\n"
        f"{text_raw}\n\n"
        f"🔗 {vk_link}\n\n"
        f"───────────────\n"
        f"💬 Готовый отклик:\n{reply}"
    )
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            await client.post(f"{_TG_API}/sendMessage", json={
                "chat_id": OWNER_CHAT_ID,
                "text":    msg,
            })
        log.info("Отправлено в Telegram: %s", text_raw[:50])
    except Exception as e:
        log.error("Telegram: %s", e)


async def run(dry_run: bool, limit: int) -> None:
    seen     = load_seen()
    cutoff   = int((datetime.now() - timedelta(days=MAX_POST_AGE_DAYS)).timestamp())
    found      = {}
    seen_texts = set()  # дедупликация по содержимому

    for query in SEARCH_QUERIES:
        posts = search_posts(query)
        for p in posts:
            key  = post_key(p)
            text = p.get("text", "")
            text_hash = hashlib.md5(text[:100].encode()).hexdigest()
            if (key not in seen
                    and key not in found
                    and text_hash not in seen_texts
                    and p.get("date", 0) >= cutoff
                    and len(text) >= MIN_TEXT_LEN
                    and is_relevant(text)):
                found[key] = p
                seen_texts.add(text_hash)
        time.sleep(0.4)

    log.info("Найдено новых релевантных постов: %d", len(found))
    if not found:
        return

    gc_token = await gigachat_token()
    processed = 0

    for key, item in found.items():
        if limit and processed >= limit:
            break

        text = item.get("text", "")
        owner_id = item.get("owner_id", 0)
        post_id  = item.get("id", 0)

        print(f"\n{'─'*50}")
        print(f"vk.com/wall{owner_id}_{post_id}")
        print(text[:200])

        reply = None
        if gc_token:
            reply = await generate_reply(gc_token, text)
            if reply:
                print(f"\nОТКЛИК:\n{reply}")

        if not dry_run and reply:
            await send_telegram(item, reply)

        seen.add(key)
        save_seen(seen)
        processed += 1
        await asyncio.sleep(1)

    log.info("Готово. Обработано: %d", processed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=1, help="Постов за запуск (по умолчанию 1)")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, args.limit))
