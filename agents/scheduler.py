"""
Секретарь — следит за ответами на комментарии группы в VK.
При обнаружении интереса уведомляет Светлану в Telegram.
Ведёт список заявок в appointments.json.

Запуск:
  python scheduler.py
"""

import io
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"

_COMMENTED_FILE    = _ROOT / "commented_posts.json"
_APPOINTMENTS_FILE = _ROOT / "appointments.json"
_ENRICHED_FILE     = _ROOT / "enriched_leads.json"

_env = dotenv_values(_ENV)
VK_TOKEN       = _env.get("VK_TOKEN", "")
VK_GROUP_ID    = _env.get("VK_GROUP_ID", "").lstrip("-")
TELEGRAM_TOKEN = _env.get("TELEGRAM_TOKEN", "")
CHAT_IDS       = [x.strip() for x in (_env.get("ALLOWED_USER_IDS") or "").split(",") if x.strip()]

_VK_API = "https://api.vk.com/method"
_VK_VER = "5.199"
_TG_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Ключевые слова — сигнал интереса
_INTEREST_KEYWORDS = [
    "напишите", "напиши", "хочу", "интересно", "как записаться",
    "запись", "сколько стоит", "цена", "консультация", "помогите",
    "можно к вам", "напишу", "свяжитесь",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("scheduler")


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_interested(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _INTEREST_KEYWORDS)


def get_comment_replies(owner_id: int, post_id: int, comment_id: int) -> list[dict]:
    try:
        r = httpx.get(f"{_VK_API}/wall.getComments", params={
            "access_token": VK_TOKEN,
            "owner_id":     owner_id,
            "post_id":      post_id,
            "comment_id":   comment_id,
            "count":        20,
            "v":            _VK_VER,
        }, timeout=15, trust_env=False)
        resp = r.json()
        if "error" in resp:
            log.warning("getComments error: %s", resp["error"]["error_msg"])
            return []
        return resp["response"].get("items", [])
    except Exception as exc:
        log.error("getComments exception: %s", exc)
        return []


def get_vk_user_name(vk_id: int) -> str:
    try:
        r = httpx.get(f"{_VK_API}/users.get", params={
            "access_token": VK_TOKEN,
            "user_ids":     vk_id,
            "v":            _VK_VER,
        }, timeout=10, trust_env=False)
        items = r.json().get("response", [])
        if items:
            u = items[0]
            return f"{u.get('first_name','')} {u.get('last_name','')}".strip()
    except Exception:
        pass
    return str(vk_id)


def notify_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        log.warning("Telegram не настроен — уведомление не отправлено")
        return
    for chat_id in CHAT_IDS:
        try:
            httpx.post(f"{_TG_API}/sendMessage",
                       json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                       timeout=10, trust_env=False)
        except Exception as exc:
            log.error("Telegram notify error: %s", exc)


def run() -> None:
    commented    = load_json(_COMMENTED_FILE)
    appointments = load_json(_APPOINTMENTS_FILE)
    enriched     = load_json(_ENRICHED_FILE)

    # индекс: vk_id → lead
    enriched_by_id = {l["vk_id"]: l for l in enriched}
    # уже обработанные ответы
    seen_reply_ids = {a["reply_comment_id"] for a in appointments}

    new_appointments = 0

    for entry in commented:
        post_id    = entry.get("post_id")
        comment_id = entry.get("comment_id")
        vk_id      = entry.get("vk_id")

        if not post_id or not comment_id:
            continue

        lead = enriched_by_id.get(vk_id, {})
        owner_id = lead.get("post_owner_id", vk_id)

        replies = get_comment_replies(owner_id, post_id, int(comment_id))

        for reply in replies:
            reply_id   = reply.get("id")
            reply_from = reply.get("from_id")
            reply_text = reply.get("text", "")

            if reply_id in seen_reply_ids:
                continue
            # игнорируем ответы от самой группы
            if str(reply_from) == f"-{VK_GROUP_ID}":
                continue

            if is_interested(reply_text):
                name = get_vk_user_name(reply_from) if reply_from else "Неизвестный"
                log.info("Интерес! %s (%s): «%s»", name, reply_from, reply_text[:80])

                appointments.append({
                    "vk_id":            reply_from,
                    "name":             name,
                    "reply_comment_id": reply_id,
                    "reply_text":       reply_text,
                    "post_id":          post_id,
                    "status":           "new",
                    "created_at":       datetime.now().isoformat(timespec="seconds"),
                })
                seen_reply_ids.add(reply_id)
                new_appointments += 1

                link = f"https://vk.com/id{reply_from}"
                notify_telegram(
                    f"🔔 <b>Новая заявка!</b>\n"
                    f"👤 {name}: <a href='{link}'>{link}</a>\n"
                    f"💬 «{reply_text[:200]}»\n\n"
                    f"Ответьте вручную или напишите мне /scheduler"
                )

    save_json(_APPOINTMENTS_FILE, appointments)

    if new_appointments:
        log.info("Новых заявок: %d", new_appointments)
    else:
        log.info("Новых ответов с интересом не найдено")


if __name__ == "__main__":
    run()
