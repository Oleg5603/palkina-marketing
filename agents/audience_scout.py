#!/usr/bin/env python3
"""
Разведчик (Scout) — аудитория для рекламного кабинета VK (см. PLAN.md, Этап 4).
Парсит участников тематических групп, фильтрует и сохраняет список ID
для загрузки в VK Реклама → Ретаргетинг → Загрузить аудиторию.

НЕ пишет людям, НЕ собирает сообщения — только публичные ID для таргетинга.
"""

import csv
import sys
import io
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SVET_BOT_ENV = Path(__file__).parent.parent / "svet_bot" / ".env"
VK_API = "https://api.vk.com/method"
VK_VER = "5.199"

TOPICS = ["психология отношений", "семейный психолог", "женская психология"]
GROUPS_PER_TOPIC = 2
MEMBERS_PER_GROUP = 1000

AGE_MIN, AGE_MAX = 28, 50
ACTIVE_DAYS = 30
IN_RELATIONSHIP_CODES = {2, 3, 4, 5, 8}  # встречается, помолвлен, женат/замужем, влюблён, в гражд. браке

EXCLUDE_GROUP_IDS = set()  # TODO: сюда добавить ID групп конкурентов-психологов, если будут известны

OUTPUT_CSV = Path(__file__).parent / "output" / "vk_audience.csv"


def vk_call(method, **params):
    env = dotenv_values(SVET_BOT_ENV)
    token = env.get("VK_USER_TOKEN")
    if not token:
        raise RuntimeError(
            "VK_USER_TOKEN не задан в svet_bot/.env.\n"
            "groups.search/groups.getMembers требуют ЛИЧНЫЙ токен пользователя VK "
            "(токен сообщества VK_TOKEN для этого не подходит).\n"
            "Получить: vk.com/dev → Мои приложения → создать Standalone-приложение → "
            "получить токен пользователя с правами 'groups' → добавить в svet_bot/.env "
            "строку VK_USER_TOKEN=..."
        )
    params["access_token"] = token
    params["v"] = VK_VER
    r = httpx.get(f"{VK_API}/{method}", params=params, timeout=15)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error'].get('error_msg')}")
    return data["response"]


def search_groups(topic, count):
    resp = vk_call("groups.search", q=topic, count=count, type="group")
    return [g["id"] for g in resp.get("items", []) if g["id"] not in EXCLUDE_GROUP_IDS]


def get_members(group_id, limit):
    ids, offset = [], 0
    while offset < limit:
        batch = min(1000, limit - offset)
        resp = vk_call("groups.getMembers", group_id=group_id, offset=offset, count=batch)
        items = resp.get("items", [])
        ids.extend(items)
        if len(items) < batch:
            break
        offset += batch
        time.sleep(0.34)  # ~3 запроса/сек, лимит VK API
    return ids


def enrich(user_ids):
    """users.get батчами по 1000, возвращает только нужные публичные поля."""
    out = []
    for i in range(0, len(user_ids), 1000):
        chunk = user_ids[i:i + 1000]
        resp = vk_call("users.get", user_ids=",".join(map(str, chunk)),
                        fields="bdate,relation,last_seen")
        out.extend(resp)
        time.sleep(0.34)
    return out


def passes_filters(profile):
    bdate = profile.get("bdate", "")
    parts = bdate.split(".")
    if len(parts) != 3:
        return False  # нет полного возраста — пропускаем
    age = 2026 - int(parts[2])
    if not (AGE_MIN <= age <= AGE_MAX):
        return False

    last_seen = profile.get("last_seen", {}).get("time")
    if not last_seen or (time.time() - last_seen) > ACTIVE_DAYS * 86400:
        return False

    if profile.get("relation") not in IN_RELATIONSHIP_CODES:
        return False

    return True


def run():
    all_member_ids = set()
    for topic in TOPICS:
        for group_id in search_groups(topic, GROUPS_PER_TOPIC):
            try:
                members = get_members(group_id, MEMBERS_PER_GROUP)
                print(f"  группа {group_id} ({topic}): {len(members)} участников")
                all_member_ids.update(members)
            except RuntimeError as e:
                print(f"  ⚠️  группа {group_id} пропущена: {e}")

    print(f"\nВсего уникальных кандидатов: {len(all_member_ids)}")

    qualified = []
    member_list = list(all_member_ids)
    for i in range(0, len(member_list), 1000):
        profiles = enrich(member_list[i:i + 1000])
        qualified.extend(p["id"] for p in profiles if passes_filters(p))

    OUTPUT_CSV.parent.mkdir(exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id"])
        for uid in qualified:
            writer.writerow([uid])

    print(f"Прошли фильтр (28-50 лет, активны {ACTIVE_DAYS} дн., в отношениях): {len(qualified)}")
    print(f"Сохранено: {OUTPUT_CSV}")


if __name__ == "__main__":
    run()
