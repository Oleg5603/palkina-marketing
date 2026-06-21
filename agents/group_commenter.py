"""
Комментатор постов в тематических группах VK.
Ищет свежие посты о боли в отношениях в публичных группах,
комментирует от имени группы misemia.

Работает с VK_TOKEN (community token) — wall.createComment + from_group.
НЕ требует Standalone.

Запуск:
  python group_commenter.py
  python group_commenter.py --dry-run
  python group_commenter.py --limit 5   — сколько групп проверять
"""

import argparse
import asyncio
import io
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"

_COMMENTED_FILE = _ROOT / "group_commented_posts.json"

_env = dotenv_values(_ENV)
VK_TOKEN             = _env.get("VK_TOKEN", "")
VK_USER_TOKEN        = _env.get("VK_USER_TOKEN", "")
VK_GROUP_ID          = _env.get("VK_GROUP_ID", "").lstrip("-")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")

_VK_API  = "https://api.vk.com/method"
_VK_VER  = "5.199"
_GC_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API  = "https://gigachat.devices.sberbank.ru/api/v1"

# Тематические группы для поиска постов (активные, проверено)
# Только психология отношений — без религиозных и медицинских групп
TARGET_GROUPS = [
    "-154905751",  # psynlpgo — психология, активна
    "-198115795",  # freudian_slips — психология отношений, активна
    "-227580727",  # vikadmitrieva_psiholog — семейная психология, активна, 104+ лайка
    "-234378574",  # club234378574 — психология, активна
]

# Посты не старше X дней
MAX_POST_AGE_DAYS = 3
# Дневной лимит комментариев
DAILY_LIMIT = 3
# Минимум лайков/комментов у поста (не спамим мёртвые посты)
MIN_LIKES = 2

_PAIN_KEYWORDS = [
    "не понимает", "устала", "одна", "обиделась", "ссора", "развод",
    "изменил", "изменила", "не слышит", "не ценит", "уходит", "расстались",
    "не могу", "больно", "одиночество", "предал", "доверие", "кризис",
    "разлюбил", "нет сил", "терпеть", "токсич", "манипул"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("group_commenter")

_SYSTEM = """Ты — представитель психотерапевтической практики, специализирующейся на отношениях и парах.
Пишешь короткий комментарий к посту ВКонтакте.

Правила:
- 2–3 предложения. Тёплый, человечный тон. Без пафоса и шаблонов.
- Первое предложение — отклик на конкретную ситуацию.
- Второе — короткая мысль, которая помогает иначе взглянуть на проблему.
- Последнее предложение строго: "Знаю психотерапевта по отношениям — если интересно, напишите нам."
- Никаких эмодзи в начале. Один эмодзи в конце допустим.
- Не упоминать цену, запись, сессии."""


def load_commented() -> dict:
    if not _COMMENTED_FILE.exists():
        return {}
    return json.loads(_COMMENTED_FILE.read_text(encoding="utf-8"))


def save_commented(data: dict) -> None:
    _COMMENTED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today_count(commented: dict) -> int:
    today = datetime.now().date().isoformat()
    return sum(1 for v in commented.values() if v.get("date", "").startswith(today))


def has_pain(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _PAIN_KEYWORDS)


def get_group_posts(group_id: str, count: int = 20) -> list[dict]:
    try:
        r = httpx.get(f"{_VK_API}/wall.get", params={
            "access_token": VK_USER_TOKEN,
            "owner_id":     group_id,
            "count":        count,
            "filter":       "owner",
            "v":            _VK_VER,
        }, timeout=15, trust_env=False)
        data = r.json()
        if "error" in data:
            log.warning("wall.get %s: %s", group_id, data["error"]["error_msg"])
            return []
        return data["response"].get("items", [])
    except Exception as exc:
        log.warning("wall.get %s exception: %s", group_id, exc)
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
    except Exception as exc:
        log.error("GigaChat token error: %s", exc)
        return None


async def generate_comment(gc_token: str, post_text: str) -> str | None:
    excerpt = post_text[:400]
    try:
        async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as client:
            r = await client.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": f"Пост: {excerpt}"},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.75,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.error("GigaChat generate error: %s", exc)
        return None


async def post_comment(owner_id: int, post_id: int, text: str) -> tuple[bool, str]:
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        r = await client.post(f"{_VK_API}/wall.createComment", data={
            "access_token": VK_USER_TOKEN,
            "owner_id":     owner_id,
            "post_id":      post_id,
            "message":      text,
            "v":            _VK_VER,
        })
        resp = r.json()
        if "error" in resp:
            return False, resp["error"]["error_msg"]
        return True, str(resp["response"]["comment_id"])


async def run(dry_run: bool, group_limit: int) -> None:
    commented = load_commented()
    if today_count(commented) >= DAILY_LIMIT:
        log.info("Дневной лимит %d достигнут", DAILY_LIMIT)
        return

    gc_token = await gigachat_token()
    if not gc_token:
        log.error("Нет токена GigaChat — выход")
        return

    cutoff = datetime.now() - timedelta(days=MAX_POST_AGE_DAYS)
    cutoff_ts = int(cutoff.timestamp())
    posted = 0

    for group_domain in TARGET_GROUPS[:group_limit]:
        if today_count(commented) >= DAILY_LIMIT:
            break

        log.info("Проверяю группу: %s", group_domain)
        posts = get_group_posts(group_domain)
        time.sleep(0.35)

        for post in posts:
            if today_count(commented) >= DAILY_LIMIT:
                break

            post_id   = post["id"]
            owner_id  = post["owner_id"]
            post_key  = f"{owner_id}_{post_id}"
            text      = post.get("text", "")
            date_ts   = post.get("date", 0)
            likes     = post.get("likes", {}).get("count", 0)

            if post_key in commented:
                continue
            if date_ts < cutoff_ts:
                continue
            if likes < MIN_LIKES:
                continue
            if not has_pain(text) or len(text) < 50:
                continue

            log.info("Подходящий пост: vk.com/wall%s_%s (лайков: %d)", owner_id, post_id, likes)
            comment_text = await generate_comment(gc_token, text)
            if not comment_text:
                continue

            print(f"\n--- Пост: vk.com/wall{owner_id}_{post_id} [{group_domain}] ---")
            print(f"Текст поста (начало): {text[:100]}...")
            print(f"Комментарий:\n{comment_text}\n")

            if dry_run:
                log.info("--dry-run: не публикуем")
                commented[post_key] = {"date": "dry-run", "group": group_domain}
                continue

            ok, result = await post_comment(owner_id, post_id, comment_text)
            if ok:
                log.info("Комментарий #%s опубликован", result)
                commented[post_key] = {
                    "comment_id": result,
                    "date": datetime.now().isoformat(timespec="seconds"),
                    "group": group_domain,
                }
                posted += 1
            else:
                log.error("Ошибка: %s", result)

        save_commented(commented)

    log.info("Готово. Опубликовано комментариев сегодня: %d", today_count(commented))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=5, help="Сколько групп проверять")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, args.limit))
