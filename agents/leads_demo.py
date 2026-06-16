#!/usr/bin/env python3
"""
Демо мультиагентного конвейера обработки входящих лидов (см. CLAUDE.md).
Источник лидов — только входящие: заявки с лендинга, сообщения в Telegram-боте.
Работает на примерных данных, без реальных токенов и без обращения к незнакомцам.
"""

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOT_KEYWORDS = ["срочно", "сегодня", "развод", "уже не могу", "записаться", "сколько стоит"]
WARM_KEYWORDS = ["думаю", "присматриваюсь", "интересует", "узнать"]
COLD_KEYWORDS = ["просто смотрю", "пока не решил", "может быть"]

# ── примерные входящие (заявки с лендинга + сообщения Telegram-бота) ──
SAMPLE_LEADS = [
    {"id": 1, "source": "landing_form", "name": "Анна",
     "text": "Здравствуйте! Хотим с мужем записаться на сессию, у нас срочно — отношения на грани развода."},
    {"id": 2, "source": "telegram_bot", "name": "Игорь",
     "text": "Сколько стоит консультация для пары? Хотим прийти сегодня вечером, если можно."},
    {"id": 3, "source": "telegram_bot", "name": "Мария",
     "text": "Я просто присматриваюсь, читаю пока статьи на канале, спасибо за контент."},
    {"id": 4, "source": "landing_form", "name": "Светлана П.",
     "text": "Интересует семейная терапия, но пока не решили с мужем, может быть через месяц."},
    {"id": 5, "source": "telegram_bot", "name": "Олег",
     "text": "Подскажите формат работы. Пока просто смотрю варианты психологов."},
]


# ── Разведчик (Scout) ──────────────────────────────────────────────
def scout_collect():
    """В реальной системе: читает новые заявки с лендинга (Formspree) и сообщения Telegram-бота."""
    return SAMPLE_LEADS


# ── Квалификатор (Qualifier) ───────────────────────────────────────
def qualify(lead):
    text = lead["text"].lower()
    if any(k in text for k in HOT_KEYWORDS):
        return "hot"
    if any(k in text for k in COLD_KEYWORDS):
        return "cold"
    if any(k in text for k in WARM_KEYWORDS):
        return "warm"
    return "warm"


# ── Исследователь (Researcher) ─────────────────────────────────────
def research(lead):
    source_label = {"landing_form": "заявка с лендинга", "telegram_bot": "сообщение в Telegram-боте"}
    return f"{source_label.get(lead['source'], lead['source'])}"


# ── Копирайтер / SDR Agent ─────────────────────────────────────────
def draft_message(lead, status):
    name = lead["name"]
    if status == "hot":
        return f"{name}, добрый день! Спасибо за обращение. Светлана готова принять в ближайшее время — подскажите удобный день и время для сессии?"
    if status == "warm":
        return f"{name}, спасибо за интерес! Расскажу подробнее о формате работы — какие вопросы для вас сейчас важнее всего?"
    return f"{name}, спасибо, что заглянули. Если появятся вопросы — мы на связи."


# ── Секретарь (Scheduler) — заглушка для hot-лидов ────────────────
def schedule_note(lead):
    return f"Эскалация Светлане: связаться с {lead['name']} напрямую для записи."


# ── Координатор (Orchestrator) ─────────────────────────────────────
def run_pipeline():
    leads = scout_collect()
    report = {"hot": [], "warm": [], "cold": []}

    for lead in leads:
        status = qualify(lead)
        context = research(lead)
        message = draft_message(lead, status)
        entry = {**lead, "status": status, "context": context, "message": message}
        if status == "hot":
            entry["action"] = schedule_note(lead)
        report[status].append(entry)

    return report


def print_report(report):
    print("=" * 70)
    print("ОТЧЁТ КООРДИНАТОРА — обработка входящих лидов")
    print("=" * 70)

    print(f"\n🔥 ГОРЯЧИЕ ({len(report['hot'])}) — требуют действия Светланы сейчас:")
    for e in report["hot"]:
        print(f"  #{e['id']} {e['name']} [{e['context']}]")
        print(f"      Сообщение: \"{e['text']}\"")
        print(f"      Ответ:     {e['message']}")
        print(f"      Действие:  {e['action']}")

    print(f"\n🌤  ТЁПЛЫЕ ({len(report['warm'])}) — прогрев, без срочности:")
    for e in report["warm"]:
        print(f"  #{e['id']} {e['name']} [{e['context']}]: {e['message']}")

    print(f"\n❄️  ХОЛОДНЫЕ ({len(report['cold'])}) — оставить в воронке прогрева:")
    for e in report["cold"]:
        print(f"  #{e['id']} {e['name']} [{e['context']}]")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    print_report(run_pipeline())
