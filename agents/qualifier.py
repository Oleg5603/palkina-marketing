"""
Квалификатор — оценивает лидов из audience_scout (CSV) через GigaChat.

Вход:  output/vk_audience.csv  (VK user IDs от audience_scout.py)
Выход: qualified_leads.json    (score >= SCORE_THRESHOLD)

Запуск:
  python qualifier.py
"""

import asyncio
import csv
import io
import json
import logging
import sys
import time
import uuid
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_ENV  = _SVET / ".env"

_CSV_FILE       = _ROOT / "output" / "vk_audience.csv"
_QUALIFIED_FILE = _ROOT / "qualified_leads.json"

_env = dotenv_values(_ENV)
VK_TOKEN             = _env.get("VK_USER_TOKEN") or _env.get("VK_TOKEN", "")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")

_VK_API  = "https://api.vk.com/method"
_VK_VER  = "5.199"
_GC_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API  = "https://gigachat.devices.sberbank.ru/api/v1"

SCORE_THRESHOLD = 6  # минимальный балл для квалификации
BATCH_SIZE      = 100  # пользователей за один запрос users.get

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("qualifier")

_SYSTEM = """Ты — квалификатор лидов для психотерапевта, специализирующегося на отношениях и парах.
Оцени профиль ВКонтакте по шкале 0–10: насколько этот человек может быть заинтересован
в работе с психотерапевтом по теме отношений.

Критерии для высокого балла (7–10):
- В статусе, «О себе» или интересах — упоминание отношений, семьи, саморазвития, психологии
- Возраст 25–50 лет
- Активный пользователь

Критерии для низкого балла (0–3):
- Бизнес-аккаунт, паблик, магазин
- Закрытый профиль без описания
- Очевидно нерелевантные интересы (авто, спорт без личного контента)

Верни JSON: {"score": <0-10>, "reason": "<одно предложение>"}"""


def load_csv_ids() -> list[int]:
    if not _CSV_FILE.exists():
        log.error("Файл не найден: %s — сначала запустите audience_scout.py", _CSV_FILE)
        return []
    with open(_CSV_FILE, newline="", encoding="utf-8") as f:
        return [int(row["user_id"]) for row in csv.DictReader(f) if row.get("user_id")]


def load_qualified() -> list[dict]:
    if not _QUALIFIED_FILE.exists():
        return []
    return json.loads(_QUALIFIED_FILE.read_text(encoding="utf-8"))


def save_qualified(leads: list[dict]) -> None:
    _QUALIFIED_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")


def vk_get_profiles(user_ids: list[int]) -> list[dict]:
    profiles = []
    for i in range(0, len(user_ids), BATCH_SIZE):
        chunk = user_ids[i:i + BATCH_SIZE]
        try:
            r = httpx.get(f"{_VK_API}/users.get", params={
                "access_token": VK_TOKEN,
                "user_ids": ",".join(map(str, chunk)),
                "fields": "about,status,interests,bdate,last_seen,sex",
                "v": _VK_VER,
            }, timeout=15, trust_env=False)
            resp = r.json()
            if "error" in resp:
                log.warning("users.get error: %s", resp["error"]["error_msg"])
            else:
                profiles.extend(resp.get("response", []))
        except Exception as exc:
            log.error("users.get exception: %s", exc)
        time.sleep(0.35)
    return profiles


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
        log.error("GigaChat token: %s", exc)
        return None


async def score_profile(gc_token: str, profile: dict) -> tuple[int, str]:
    text = " | ".join(filter(None, [
        profile.get("about", ""),
        profile.get("status", ""),
        profile.get("interests", ""),
    ])).strip()

    if not text:
        return 2, "пустой профиль"

    try:
        async with httpx.AsyncClient(verify=False, timeout=20, trust_env=False) as client:
            r = await client.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": f"Профиль: {text[:400]}"},
                    ],
                    "max_tokens": 80,
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            start = content.find("{")
            end   = content.rfind("}") + 1
            data  = json.loads(content[start:end])
            return int(data.get("score", 0)), data.get("reason", "")
    except Exception as exc:
        log.error("GigaChat score error: %s", exc)
        return 0, str(exc)


async def run() -> None:
    all_ids      = load_csv_ids()
    existing     = load_qualified()
    existing_ids = {l["vk_id"] for l in existing}

    new_ids = [i for i in all_ids if i not in existing_ids]
    if not new_ids:
        log.info("Нет новых кандидатов")
        return

    log.info("Загружаю профили: %d кандидатов", len(new_ids))
    profiles = vk_get_profiles(new_ids)

    gc_token = await gigachat_token()
    if not gc_token:
        log.warning("GigaChat недоступен — используем только правила (score=5 по умолчанию)")

    new_qualified = 0
    for profile in profiles:
        vk_id = profile["id"]
        name  = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()

        if gc_token:
            score, reason = await score_profile(gc_token, profile)
        else:
            score, reason = 5, "GigaChat недоступен"

        if score >= SCORE_THRESHOLD:
            existing.append({
                "vk_id":  vk_id,
                "name":   name,
                "score":  score,
                "reason": reason,
                "status": "qualified",
            })
            new_qualified += 1
            log.info("✅ %s (%s) — score %d: %s", name, vk_id, score, reason)
        else:
            log.debug("❌ %s (%s) — score %d: %s", name, vk_id, score, reason)

    save_qualified(existing)
    log.info("Квалифицировано новых: %d / %d", new_qualified, len(profiles))


if __name__ == "__main__":
    asyncio.run(run())
