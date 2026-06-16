#!/usr/bin/env python3
"""
Копит уникальных реальных лидов из VK-группы (исключая спам и тестовые сообщения
владельца) и при достижении порога (3) уведомляет в Telegram через svet_bot.
Состояние — agents/seen_leads.json, накопление между запусками.

Запуск (например, по расписанию): python check_new_clients.py
"""

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values

from leads_demo import vk_scout_collect, SVET_BOT_ENV  # сама настраивает utf-8 stdout

STATE_FILE = Path(__file__).parent / "seen_leads.json"
THRESHOLD = 3
EXCLUDE_PEER_IDS = {77790943}  # Олег Палкин — тестовое сообщение, не клиент


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"seen": {}, "notified_at": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(seen):
    env = dotenv_values(SVET_BOT_ENV)
    token = env.get("TELEGRAM_TOKEN")
    chat_ids = [x.strip() for x in (env.get("ALLOWED_USER_IDS") or "").split(",") if x.strip()]
    if not token or not chat_ids:
        print("⚠️  Не отправлено: TELEGRAM_TOKEN/ALLOWED_USER_IDS не заданы")
        return
    names = ", ".join(seen.values())
    text = f"🎉 Набралось {len(seen)} реальных клиентов в VK-группе: {names}"
    for chat_id in chat_ids:
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat_id, "text": text}, timeout=10)


def main():
    state = load_state()
    seen = state["seen"]

    for lead in vk_scout_collect():
        peer_id = str(lead["id"])
        if lead["id"] in EXCLUDE_PEER_IDS:
            continue
        if peer_id not in seen:
            seen[peer_id] = lead["name"]

    save_state(state)
    print(f"Уникальных реальных лидов накоплено: {len(seen)}/{THRESHOLD}")

    if len(seen) >= THRESHOLD and not state.get("notified_at"):
        notify(seen)
        state["notified_at"] = "sent"
        save_state(state)
        print("THRESHOLD_REACHED")


if __name__ == "__main__":
    main()
