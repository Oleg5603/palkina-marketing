"""
Комментатор — генерирует и публикует комментарий к посту лида от имени группы.

Вход:  enriched_leads.json  (поле status == "researched")
Выход: обновляет статус на "commented", сохраняет в enriched_leads.json
       ведёт лог в commented_posts.json (защита от повторных комментариев)

Запуск:
  python commenter.py
  python commenter.py --dry-run   — генерирует комментарий, не публикует
"""

import argparse
import asyncio
import io
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"

_ENRICHED_FILE  = _ROOT / "enriched_leads.json"
_COMMENTED_FILE = _ROOT / "commented_posts.json"

_env = dotenv_values(_ENV)
VK_TOKEN             = _env.get("VK_TOKEN", "")
VK_USER_TOKEN        = _env.get("VK_USER_TOKEN", "")
VK_GROUP_ID          = _env.get("VK_GROUP_ID", "").lstrip("-")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")

_VK_API  = "https://api.vk.com/method"
_VK_VER  = "5.199"
_GC_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API  = "https://gigachat.devices.sberbank.ru/api/v1"

# Лимит: не более 3 комментариев в день
_DAILY_LIMIT = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("commenter")

_SYSTEM = """Ты — психотерапевт Светлана Палкина, специализируешься на отношениях и парах.
Пишешь короткий комментарий к посту человека ВКонтакте от имени группы.

Правила:
- 2–3 предложения. Тёплый, человечный тон. Без пафоса и шаблонов.
- Первое предложение — отклик на конкретную ситуацию из цитаты.
- Второе — короткая мысль, которая помогает иначе взглянуть на ситуацию.
- Последнее предложение строго: "Знаю психотерапевта по отношениям — если интересно, напишите нам."
- Никаких эмодзи в начале. Один эмодзи в конце допустим.
- Не упоминать цену, запись, сессии."""


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def today_comment_count(commented: list) -> int:
    today = datetime.now().date().isoformat()
    return sum(1 for c in commented if c.get("date", "").startswith(today))


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


async def generate_comment(gc_token: str, pain_tags: list, excerpt: str) -> str | None:
    tags_str = ", ".join(pain_tags) if pain_tags else "одиночество, отношения"
    user_msg = f'Тема поста: {tags_str}. Цитата из поста: "{excerpt}"'
    try:
        async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as client:
            r = await client.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": user_msg},
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
    """Сначала пробует от имени группы (для постов в сообществах),
    при отказе — от личного аккаунта (для личных стен)."""
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        # Попытка 1: от имени группы
        try:
            r = await client.post(f"{_VK_API}/wall.createComment", data={
                "access_token": VK_TOKEN,
                "owner_id":     owner_id,
                "post_id":      post_id,
                "message":      text,
                "from_group":   VK_GROUP_ID,
                "v":            _VK_VER,
            })
            resp = r.json()
            if "error" not in resp:
                return True, str(resp["response"]["comment_id"])
            err_msg = resp["error"]["error_msg"]
            log.info("Группа не может комментировать (личная стена) — пробую личный аккаунт: %s", err_msg)
        except Exception as exc:
            log.warning("Ошибка при комментировании от группы: %s", exc)

        # Попытка 2: от личного аккаунта (VK_USER_TOKEN)
        if not VK_USER_TOKEN:
            return False, "VK_USER_TOKEN не задан для комментирования личных стен"
        try:
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
        except Exception as exc:
            return False, str(exc)


async def run(dry_run: bool) -> None:
    enriched  = load_json(_ENRICHED_FILE)
    commented = load_json(_COMMENTED_FILE)
    commented_post_ids = {c["post_id"] for c in commented}

    if today_comment_count(commented) >= _DAILY_LIMIT:
        log.info("Дневной лимит %d комментариев достигнут", _DAILY_LIMIT)
        return

    to_comment = [
        l for l in enriched
        if l.get("status") == "researched"
        and l.get("post_id") not in commented_post_ids
    ]

    if not to_comment:
        log.info("Нет лидов для комментирования")
        return

    gc_token = await gigachat_token()
    if not gc_token:
        log.error("Нет токена GigaChat — выход")
        return

    for lead in to_comment:
        if today_comment_count(commented) >= _DAILY_LIMIT:
            log.info("Лимит достигнут, остановка")
            break

        vk_id      = lead["vk_id"]
        post_id    = lead["post_id"]
        owner_id   = lead["post_owner_id"]
        pain_tags  = lead.get("pain_tags", [])
        excerpt    = lead.get("post_excerpt", "")

        log.info("Генерирую комментарий для %s | пост %s | боль: %s",
                 lead.get("name", vk_id), post_id, pain_tags)

        comment_text = await generate_comment(gc_token, pain_tags, excerpt)
        if not comment_text:
            log.error("Не удалось сгенерировать комментарий для %s", vk_id)
            continue

        print(f"\n--- Комментарий для {lead.get('name', vk_id)} ---")
        print(f"Пост: vk.com/wall{owner_id}_{post_id}")
        print(f"Боль: {pain_tags}")
        print(f"Текст:\n{comment_text}\n")

        if dry_run:
            log.info("--dry-run: комментарий не опубликован")
            continue

        ok, result = await post_comment(owner_id, post_id, comment_text)
        if ok:
            log.info("Опубликован комментарий #%s", result)
            lead["status"] = "commented"
            lead["commented_at"] = datetime.now().isoformat(timespec="seconds")
            commented.append({
                "post_id":   post_id,
                "vk_id":     vk_id,
                "comment_id": result,
                "date":      datetime.now().isoformat(timespec="seconds"),
            })
        else:
            log.error("Ошибка публикации комментария: %s", result)

    save_json(_ENRICHED_FILE, enriched)
    save_json(_COMMENTED_FILE, commented)
    log.info("Готово")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
