"""
Оркестратор публикаций — проект «Психотерапевт» (Светлана Палкина)

Роль Копирайтер/Coordinator из CLAUDE.md:
  1. Берёт следующую тему из topics.json (ротация по индексу)
  2. GigaChat генерирует текст поста
  3. Pollinations.ai генерирует фото
  4. Публикует пост в VK-группу misemia
  5. Логирует результат в content_log.json

Запуск:
  python content_agent.py              — публикует следующую тему
  python content_agent.py --dry-run    — генерирует и показывает, не публикует
  python content_agent.py --topic "Своя тема" — задать тему вручную
"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Windows cp1251 не умеет в эмодзи — переключаем stdout на UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

# ── Пути ──────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent
_SVET = _ROOT.parent / "svet_bot"
_TOPICS_FILE = _SVET / "topics.json"
_STATE_FILE = _ROOT / "content_state.json"
_LOG_FILE = _ROOT / "content_log.json"
_LOCK_FILE = _ROOT / "content_agent.lock"
_ENV_FILE = _SVET / ".env"

# ── Конфиг ────────────────────────────────────────────────────────────────────

_env = dotenv_values(_ENV_FILE)
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")
VK_TOKEN = _env.get("VK_TOKEN", "")          # community token — wall.post
VK_USER_TOKEN = _env.get("VK_USER_TOKEN", "") # личный токен — photo upload
VK_GROUP_ID = _env.get("VK_GROUP_ID", "").lstrip("-")

_GIGACHAT_AUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GIGACHAT_API = "https://gigachat.devices.sberbank.ru/api/v1"
_VK_API = "https://api.vk.com/method"
_VK_VER = "5.199"

# Дружеский стиль (посты 1, 2, 3, 5, 6, 7, …)
_PROMPT_FRIENDLY = """Ты — помощник психотерапевта Светланы Палкиной, которая специализируется
на супружеских и партнёрских отношениях. Пишешь посты для её страницы ВКонтакте.

Правила:
- Тёплый, доверительный тон. Без агрессии и давления.
- 200–350 слов.
- Используй 3–5 эмодзи по тексту — в начале абзацев или ключевых мыслях (💛🌿🤝💬✨).
- Выделяй жирным ключевые мысли и важные фразы двойными звёздочками: **вот так**. Выделяй 3–5 фраз на пост.
- Структура: цепляющий первый абзац → мысль или короткая история → вывод → мягкий призыв.
- В конце добавь 4–6 хэштегов: #психолог #отношения #семья #пары и по теме поста.
- Заканчивай фразой «Если откликается — напишите мне».
- Не используй слова: экзистенциальный, нарратив, контейнировать, триггер."""

# Провокативный стиль (каждый 4-й пост)
_PROMPT_PROVOCATIVE = """Ты — помощник психотерапевта Светланы Палкиной. Пишешь посты для ВКонтакте.

Сегодня нужен провокативный пост — цепляющий, неудобный, заставляющий задуматься.

Правила:
- Начни с резкого, провокационного утверждения или неудобного вопроса. Без вступлений.
- Тон: честный, смелый, без прикрас — но не агрессивный и не осуждающий.
- 200–300 слов.
- Используй 2–3 эмодзи — сдержанно, только там где усиливают эффект (🔥⚡💥).
- Выделяй ключевые провокационные фразы двойными звёздочками: **вот так**. 3–4 фразы.
- Структура: провокация → неудобная правда → выход → призыв к честному разговору.
- В конце добавь 4–6 хэштегов: #психолог #отношения #правда #пары и по теме поста.
- Заканчивай фразой «Если откликается — напишите мне».
- Не используй слова: экзистенциальный, нарратив, контейнировать, триггер."""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("content_agent")


def _read_json(path: Path) -> dict | list:
    """Читает JSON с защитой от BOM (PowerShell utf-8-sig)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    return json.loads(text)


@contextmanager
def _lock():
    """Предотвращает одновременный запуск двух экземпляров скрипта."""
    if _LOCK_FILE.exists():
        pid = _LOCK_FILE.read_text().strip()
        log.error("Уже запущен (pid %s). Удалите %s если процесс завис.", pid, _LOCK_FILE)
        sys.exit(1)
    _LOCK_FILE.write_text(str(os.getpid()))
    try:
        yield
    finally:
        _LOCK_FILE.unlink(missing_ok=True)


# ── Ротация тем ───────────────────────────────────────────────────────────────

def pick_topic(manual: str | None = None) -> tuple[str, int, int]:
    """Возвращает (тема, idx, post_count). idx=-1 если тема задана вручную."""
    topics = _read_json(_TOPICS_FILE)
    state = _read_json(_STATE_FILE) if _STATE_FILE.exists() else {}
    post_count = state.get("post_count", 0)
    if manual:
        return manual, -1, post_count
    idx = state.get("next_topic_index", 0) % len(topics)
    return topics[idx], idx, post_count


def pick_style(post_count: int) -> str:
    """Каждый 4-й пост (0-индекс: 3, 7, 11, …) — провокативный, остальные — дружеский."""
    if (post_count + 1) % 4 == 0:
        log.info("Стиль: ПРОВОКАТИВНЫЙ (пост #%d)", post_count + 1)
        return _PROMPT_PROVOCATIVE
    log.info("Стиль: дружеский (пост #%d)", post_count + 1)
    return _PROMPT_FRIENDLY


def save_state(idx: int, post_count: int) -> None:
    if idx < 0:
        return
    topics = _read_json(_TOPICS_FILE)
    state = {
        "next_topic_index": (idx + 1) % len(topics),
        "post_count": post_count + 1,
    }
    try:
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Не удалось сохранить state: %s", exc)


# ── GigaChat ──────────────────────────────────────────────────────────────────

async def gigachat_token() -> str | None:
    if not GIGACHAT_CREDENTIALS:
        return None
    try:
        async with httpx.AsyncClient(verify=False, timeout=15, trust_env=False) as client:
            r = await client.post(
                _GIGACHAT_AUTH,
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


async def generate_text(topic: str, system_prompt: str = _PROMPT_FRIENDLY) -> str | None:
    token = await gigachat_token()
    if not token:
        log.error("Нет токена GigaChat")
        return None
    try:
        async with httpx.AsyncClient(verify=False, timeout=60, trust_env=False) as client:
            r = await client.post(
                f"{_GIGACHAT_API}/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Напиши пост на тему: {topic}"},
                    ],
                    "max_tokens": 900,
                    "temperature": 0.8,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.error("GigaChat generate error: %s", exc)
        return None


# ── Pollinations.ai ───────────────────────────────────────────────────────────

_IMAGE_STYLES = [
    # 1. Кинематографичный портрет
    "Cinematic portrait, {topic}, warm golden hour light, shallow depth of field, film grain, 35mm lens, emotional expression, no text",
    # 2. Минимализм
    "Minimalist photo, {topic}, clean white background, single subject, strong shadows, high contrast black and white, editorial style, no text",
    # 3. Документальный стиль
    "Documentary photography, {topic}, candid moment, natural indoor light, raw emotion, photojournalism style, grain texture, no text",
    # 4. Акварельная иллюстрация
    "Watercolor illustration, {topic}, soft pastel colors, flowing brushstrokes, dreamy atmosphere, artistic, gentle, no text",
    # 5. Абстрактное искусство
    "Abstract art, {topic}, bold geometric shapes, deep blues and warm oranges, symbolism, modern gallery style, no photograph, no text",
    # 6. Вечерний интерьер
    "Interior photography, {topic}, cozy evening atmosphere, warm lamp light, bokeh, couple silhouettes, lifestyle magazine style, no text",
    # 7. Природа как метафора
    "Nature metaphor photo, {topic}, two trees intertwining, sunrise mist, forest path, symbolic, wide angle, dramatic sky, no people, no text",
    # 8. Графика / постер
    "Modern graphic design poster, {topic}, bold typography replaced by shapes, duotone color scheme, Bauhaus style, contemporary art, no text",
]

async def generate_image(topic: str) -> bytes | None:
    import random as _random
    seed = _random.randint(1, 99999)
    style = _random.choice(_IMAGE_STYLES)
    prompt = style.format(topic=topic)
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + f"?model=flux-realism&width=1024&height=1024&nologo=true&enhance=true&seed={seed}"
    )
    log.info("Стиль изображения: %s", style[:60])
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True, trust_env=False) as client:
            r = await client.get(url)
            r.raise_for_status()
            log.info("Фото сгенерировано: %d байт", len(r.content))
            return r.content
    except Exception as exc:
        log.error("Pollinations error: %s", exc)
        return None


# ── VK publish ────────────────────────────────────────────────────────────────

async def publish_to_vk(text: str, photo: bytes | None, group_id: str = "") -> tuple[bool, str]:
    gid = (group_id or VK_GROUP_ID).lstrip("-")
    if not VK_TOKEN or not gid:
        return False, "VK_TOKEN или VK_GROUP_ID не заданы в .env"

    owner_id = f"-{gid}"
    # Для загрузки фото нужен личный токен пользователя (community token не может)
    photo_token = VK_USER_TOKEN or VK_TOKEN

    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            attachment = ""

            if photo is not None:
                if not VK_USER_TOKEN:
                    log.warning("VK_USER_TOKEN не задан — публикуем без фото. "
                                "Добавьте личный токен в svet_bot/.env")
                else:
                    r = await client.get(f"{_VK_API}/photos.getWallUploadServer", params={
                        "access_token": photo_token, "group_id": gid, "v": _VK_VER,
                    })
                    r.raise_for_status()
                    resp = r.json()
                    if "error" in resp:
                        return False, f"getWallUploadServer: {resp['error']['error_msg']}"
                    else:
                        upload_url = resp["response"]["upload_url"]
                        r = await client.post(
                            upload_url,
                            files={"photo": ("photo.jpg", io.BytesIO(photo), "image/jpeg")},
                        )
                        r.raise_for_status()
                        upload_data = r.json()
                        log.info("Фото загружено: %s", upload_data)

                        r = await client.get(f"{_VK_API}/photos.saveWallPhoto", params={
                            "access_token": VK_USER_TOKEN,
                            "group_id": gid,
                            "photo": upload_data["photo"],
                            "server": upload_data["server"],
                            "hash": upload_data["hash"],
                            "v": _VK_VER,
                        })
                        r.raise_for_status()
                        resp = r.json()
                        if "error" in resp:
                            return False, f"saveWallPhoto: {resp['error']['error_msg']}"
                        else:
                            saved = resp["response"][0]
                            attachment = f"photo{saved['owner_id']}_{saved['id']}"
                            log.info("Фото сохранено: %s", attachment)

            # Если фото не прикрепилось — не публикуем пост без картинки
            if photo is not None and not attachment:
                return False, "Фото не прикреплено к посту — публикация отменена"

            r = await client.post(f"{_VK_API}/wall.post", data={
                "access_token": VK_TOKEN,
                "owner_id": owner_id,
                "message": text,
                "from_group": 1,
                "attachments": attachment,
                "v": _VK_VER,
            })
            r.raise_for_status()
            resp = r.json()
            if "error" in resp:
                return False, f"wall.post: {resp['error']['error_msg']}"

            post_id = resp["response"]["post_id"]
            url = f"https://vk.com/wall{owner_id}_{post_id}"
            return True, url

    except Exception as exc:
        import traceback as _tb
        log.error("VK publish error: %s\n%s", exc, _tb.format_exc())
        return False, str(exc) or repr(exc)


# ── Лог результата ────────────────────────────────────────────────────────────

def save_log(topic: str, ok: bool, result: str, dry_run: bool) -> None:
    try:
        entries = []
        if _LOG_FILE.exists():
            entries = _read_json(_LOG_FILE)
        entries.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "topic": topic,
            "ok": ok,
            "result": result,
            "dry_run": dry_run,
        })
        _LOG_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Не удалось записать лог: %s", exc)


# ── Главный пайплайн ──────────────────────────────────────────────────────────

def last_published_today() -> bool:
    """Возвращает True если сегодня уже был опубликован пост (не dry-run)."""
    if not _LOG_FILE.exists():
        return False
    try:
        entries = _read_json(_LOG_FILE)
        today = datetime.now().date().isoformat()
        return any(
            e.get("ts", "").startswith(today) and e.get("ok") and not e.get("dry_run")
            for e in entries
        )
    except Exception:
        return False


async def run(manual_topic: str | None, dry_run: bool, force: bool = False, group_id: str = "") -> None:
    if not dry_run and not force and not manual_topic and last_published_today():
        log.info("Пост сегодня уже опубликован. Используйте --force для повторной публикации.")
        return

    topic, idx, post_count = pick_topic(manual_topic)
    style = pick_style(post_count)
    log.info("Тема: %s", topic)

    # 1. Текст
    log.info("Генерирую текст (GigaChat)…")
    text = await generate_text(topic, style)
    if not text:
        log.error("Текст не сгенерирован — выход")
        return
    log.info("Текст готов (%d симв.)", len(text))

    # 2. Фото
    log.info("Генерирую фото (Pollinations)…")
    photo = await generate_image(topic)

    if dry_run:
        print("\n" + "=" * 60)
        print(f"ТЕМА: {topic}")
        print("=" * 60)
        print(text)
        print("=" * 60)
        print(f"ФОТО: {'сгенерировано' if photo else 'НЕТ'} ({len(photo) if photo else 0} байт)")
        print("Публикация пропущена (--dry-run)")
        save_log(topic, True, "dry-run", dry_run=True)
        return

    # 3. Публикация
    if group_id:
        log.info("Публикую в тестовую группу %s…", group_id)
    else:
        log.info("Публикую в VK…")
    ok, result = await publish_to_vk(text, photo, group_id)
    save_log(topic, ok, result, dry_run=False)

    if ok:
        if idx >= 0:
            save_state(idx, post_count)
        log.info("✅ Опубликовано: %s", result)
        print(f"\n✅ Опубликовано: {result}")
    else:
        log.error("❌ Ошибка: %s", result)
        print(f"\n❌ Ошибка публикации: {result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Публикация поста в VK-группу misemia")
    parser.add_argument("--dry-run", action="store_true", help="Генерировать, но не публиковать")
    parser.add_argument("--topic", type=str, default=None, help="Задать тему вручную")
    parser.add_argument("--force", action="store_true", help="Публиковать даже если пост уже был сегодня")
    parser.add_argument("--group-id", type=str, default="", help="ID тестовой группы (вместо основной)")
    args = parser.parse_args()
    with _lock():
        asyncio.run(run(args.topic, args.dry_run, args.force, args.group_id))
