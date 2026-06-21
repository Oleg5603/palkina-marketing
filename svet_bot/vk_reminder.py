"""
Ежедневные напоминания Светлане о шагах маркетингового плана.
Запускается 2 раза в день через Task Scheduler: 9:00 и 18:00.
"""
import os
import sys
from datetime import date

import httpx
from dotenv import load_dotenv

load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_IDS = [x.strip() for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()]
VK_USER_TOKEN = os.getenv("VK_USER_TOKEN")

# Старт плана — меняй при необходимости
PLAN_START = date(2026, 6, 19)

# Мамские группы Чайковского
MOM_GROUPS = [
    ("baby59ru", "От мамы к маме | Чайковский", "15 400 уч."),
    ("chaik_roddom", "Сообщество мам г.Чайковский", "6 800 уч."),
    ("club92750839", "От мамы к маме г.Чайковский", "6 400 уч."),
]


def get_latest_post_url(domain: str) -> str:
    """Возвращает ссылку на последний пост группы."""
    try:
        r = httpx.get(
            "https://api.vk.com/method/wall.get",
            params={"domain": domain, "count": 1, "access_token": VK_USER_TOKEN, "v": "5.199"},
            timeout=8,
        )
        items = r.json().get("response", {}).get("items", [])
        if items:
            post = items[0]
            owner_id = post.get("owner_id", "")
            post_id = post.get("id", "")
            return f"https://vk.com/{domain}?w=wall{owner_id}_{post_id}"
    except Exception:
        pass
    return f"https://vk.com/{domain}"

# Юристы Чайковского
LAWYERS = [
    ("vk.com/oleneva.elena", "Юрист Оленева Елена"),
    ("vk.com/jur_chaik", "Юристы-онлайн | Чайковский"),
    ("vk.com/urist_anton_makurov", "Юрист Антон Макуров"),
]

# План по неделям
PLAN = {
    1: {
        "title": "Неделя 1 — Позиция",
        "steps": [
            "📝 Обновить описание группы:\n«Семейный консультант для женщин в кризисе | Чайковский + онлайн по всей России»",
            "🤝 Написать юристам Чайковского с предложением взаимных рекомендаций:\n"
            + "\n".join(f"• {l[0]} — {l[1]}" for l in LAWYERS),
            "✅ Проверить: 3 поста уже опубликованы в группе (посты 47, 48, 49). Посмотреть реакцию.",
        ]
    },
    2: {
        "title": "Неделя 2 — Присутствие",
        "steps": [
            "👥 Свежие посты в мамских группах Чайковского — зайди, найди живой вопрос, оставь совет:\n"
            + "\n".join(
                f"• <a href='{get_latest_post_url(g[0])}'>{g[1]}</a> ({g[2]})"
                for g in MOM_GROUPS
            ),
            "✍️ Написать пост-историю (анонимно): «Сегодня клиентка сказала мне...» — конкретная ситуация, без советов.",
            "💬 Мониторинг групп работает автоматически — проверить Telegram на наличие постов для комментирования.",
        ]
    },
    3: {
        "title": "Неделя 3 — Сарафан",
        "steps": [
            "⭐ Попросить 1-2 клиентов написать отзыв-историю на стене группы: «Я пришла когда...»",
            "💬 Оставить 1-2 живых комментария в мамских группах — ответить на чей-то вопрос как эксперт.",
            "📊 Проверить статистику группы: сколько просмотров получили посты 47-49.",
        ]
    },
    4: {
        "title": "Неделя 4 — Итог",
        "steps": [
            "📞 Позвонить/написать юристам — уточнить, есть ли общие клиенты.",
            "🎯 Цель: 3 платных обращения за месяц. Подсчитать результат.",
            "🔄 Запланировать следующий месяц на основе того, что сработало.",
        ]
    },
}

MORNING_PREFIX = "🌅 Доброе утро, Светлана!\n\nПлан на сегодня:\n"
EVENING_PREFIX = "🌆 Вечерняя проверка:\n\nЧто сделано из плана сегодня?\n"


def get_current_step() -> str:
    today = date.today()
    day = (today - PLAN_START).days
    week = min((day // 7) + 1, 4)
    step_idx = day % 3  # rotate through steps within a week

    plan = PLAN[week]
    steps = plan["steps"]
    step = steps[step_idx % len(steps)]

    return f"<b>{plan['title']}</b>\n\n{step}"


def send_telegram(text: str):
    if not TG_TOKEN or not TG_CHAT_IDS:
        print("Telegram не настроен")
        return
    for chat_id in TG_CHAT_IDS:
        r = httpx.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        print(f"Отправлено {chat_id}:", r.status_code)


def main():
    is_evening = "--evening" in sys.argv
    prefix = EVENING_PREFIX if is_evening else MORNING_PREFIX
    step = get_current_step()
    send_telegram(prefix + step)


if __name__ == "__main__":
    main()
