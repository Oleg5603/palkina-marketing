"""
VK Group Monitor — ежедневный поиск постов для комментирования.
Проверяет целевые группы, находит свежие посты с вопросами,
отправляет Светлане в Telegram ссылки с подсказкой для комментария.

Запуск: python vk_monitor.py
Или добавить в Task Scheduler / cron на 9:00 каждый день.
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("vk_monitor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

VK_USER_TOKEN = os.getenv("VK_USER_TOKEN")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_IDS = [x.strip() for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]

VK_API = "https://api.vk.com/method"
VK_VER = "5.199"

# Целевые группы для мониторинга
TARGET_GROUPS = [
    {"domain": "club228583817",      "name": "Психология отношений | Взгляд женщины"},
    {"domain": "izmene_net_vernost", "name": "Измена. Развод. Расставание"},
    {"domain": "schastie_vnutri_tebia", "name": "Как пережить развод"},
    {"domain": "tsurantrevogastop",  "name": "Психолог отношений"},
]

# Слова-сигналы: пост скорее всего содержит вопрос или личную историю
QUESTION_SIGNALS = [
    "как мне", "что делать", "помогите", "не знаю", "подскажите",
    "у меня", "я не могу", "не могу понять", "как справиться",
    "развелась", "после развода", "муж ушёл", "изменил", "расстались",
    "не сплю", "тревога", "плачу", "боюсь", "одна", "потеряла себя",
    "устала", "выгорела", "не чувствую", "смысл", "зачем",
]

SEEN_FILE = Path(__file__).parent / "vk_monitor_seen.json"


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen)), encoding="utf-8")


def is_question_post(text: str) -> bool:
    text_lower = text.lower()
    return any(signal in text_lower for signal in QUESTION_SIGNALS)


def suggest_comment(text: str) -> str:
    """Подсказка для комментария на основе темы поста."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["развод", "развелась", "муж ушёл", "расстались"]):
        return "💬 Совет: напишите о том, что чувствовать потерю — нормально, и предложите первый разговор."
    if any(w in text_lower for w in ["изменил", "измена", "предательство"]):
        return "💬 Совет: отметьте, что недоверие после измены — это не слабость, а реакция психики."
    if any(w in text_lower for w in ["тревога", "страх", "не сплю", "паника"]):
        return "💬 Совет: объясните что тревога — сигнал, а не приговор, и поделитесь одним простым шагом."
    if any(w in text_lower for w in ["устала", "выгорела", "нет сил"]):
        return "💬 Совет: покажите что усталость от роли — это не эгоизм, а сигнал что что-то надо менять."
    return "💬 Совет: поддержите, задайте уточняющий вопрос, покажите что слышите человека."


def get_group_posts(domain: str, hours_back: int = 25) -> list[dict]:
    """Получить свежие посты группы за последние N часов."""
    since = int((datetime.now() - timedelta(hours=hours_back)).timestamp())
    try:
        r = httpx.get(f"{VK_API}/wall.get", params={
            "domain": domain,
            "count": 20,
            "access_token": VK_USER_TOKEN,
            "v": VK_VER,
        }, timeout=10)
        items = r.json().get("response", {}).get("items", [])
        return [p for p in items if p.get("date", 0) >= since]
    except Exception as e:
        log.warning("Ошибка получения постов %s: %s", domain, e)
        return []


def send_telegram(text: str):
    if not TG_TOKEN or not TG_CHAT_IDS:
        log.warning("Telegram не настроен")
        return
    for chat_id in TG_CHAT_IDS:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": True},
                timeout=10,
            )
        except Exception as e:
            log.error("Telegram ошибка (%s): %s", chat_id, e)


def run_monitor():
    seen = load_seen()
    found = []

    for group in TARGET_GROUPS:
        posts = get_group_posts(group["domain"])
        for post in posts:
            uid = f"{group['domain']}_{post['id']}"
            if uid in seen:
                continue
            text = post.get("text", "")
            if len(text) < 30:
                continue
            if is_question_post(text):
                found.append({
                    "group": group["name"],
                    "domain": group["domain"],
                    "post_id": post["id"],
                    "text": text[:200].replace("\n", " "),
                    "comments": post.get("comments", {}).get("count", 0),
                    "likes": post.get("likes", {}).get("count", 0),
                    "url": f"https://vk.com/{group['domain']}?w=wall-{post['id']}",
                    "hint": suggest_comment(text),
                })
            seen.add(uid)

    save_seen(seen)

    if not found:
        log.info("Новых постов для комментирования не найдено.")
        return

    # Формируем Telegram-сообщение
    msg = f"📋 <b>VK Мониторинг</b> — {datetime.now().strftime('%d.%m %H:%M')}\n"
    msg += f"Найдено постов для комментирования: <b>{len(found)}</b>\n\n"

    for i, p in enumerate(found[:5], 1):  # максимум 5 за раз
        short = p["text"][:120] + ("..." if len(p["text"]) > 120 else "")
        msg += f"<b>{i}. {p['group']}</b>\n"
        msg += f"💬{p['comments']} ❤️{p['likes']}\n"
        msg += f"«{short}»\n"
        msg += f"{p['hint']}\n"
        msg += f"🔗 <a href='{p['url']}'>Открыть пост</a>\n\n"

    msg += "Напишите живой комментарий — не рекламу, а поддержку или совет."
    send_telegram(msg)
    log.info("Отправлено %d постов в Telegram.", len(found))


if __name__ == "__main__":
    run_monitor()
