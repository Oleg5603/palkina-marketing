"""
Добавляет фото к постам группы, опубликованным без картинки.
Стратегия: удалить пост → сгенерировать фото → опубликовать заново с тем же текстом.
(wall.edit недоступен ни с одним токеном — используем wall.delete + wall.post)

Запуск:
  python fix_photos.py           — исправляет все посты без фото (последние 20)
  python fix_photos.py --dry-run — показывает что будет исправлено, без изменений
"""

import argparse
import asyncio
import io
import sys
import urllib.parse
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_SVET = Path(__file__).parent.parent / "svet_bot"
_env = dotenv_values(_SVET / ".env")

VK_TOKEN      = _env.get("VK_TOKEN", "")
VK_USER_TOKEN = _env.get("VK_USER_TOKEN", "")
VK_GROUP_ID   = _env.get("VK_GROUP_ID", "").lstrip("-")

_VK  = "https://api.vk.com/method"
_VER = "5.199"


async def get_posts_without_photo() -> list[dict]:
    async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
        r = await c.get(f"{_VK}/wall.get", params={
            "owner_id": f"-{VK_GROUP_ID}",
            "count": 20,
            "filter": "owner",
            "access_token": VK_USER_TOKEN,
            "v": _VER,
        })
        data = r.json()
        if "error" in data:
            print(f"wall.get error: {data['error']['error_msg']}")
            return []
        items = data["response"]["items"]
    return [
        p for p in items
        if not any(a.get("type") == "photo" for a in p.get("attachments", []))
    ]


async def generate_image(text: str) -> bytes | None:
    prompt = (
        "Cinematic photo related to: " + text[:120] +
        ". Real person or couple, warm natural light, soft bokeh, "
        "emotional mood, professional photography, no text, 4k"
    )
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + "?model=flux-realism&width=1024&height=1024&nologo=true&enhance=true"
    )
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True, trust_env=False) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.content
    except Exception as exc:
        print(f"  Ошибка Pollinations: {exc}")
        return None


async def upload_photo(photo: bytes) -> str | None:
    async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
        r = await c.get(f"{_VK}/photos.getWallUploadServer", params={
            "access_token": VK_USER_TOKEN,
            "group_id": VK_GROUP_ID,
            "v": _VER,
        })
        resp = r.json()
        if "error" in resp:
            print(f"  getWallUploadServer: {resp['error']['error_msg']}")
            return None

        r = await c.post(
            resp["response"]["upload_url"],
            files={"photo": ("photo.jpg", io.BytesIO(photo), "image/jpeg")},
        )
        upload_data = r.json()

        r = await c.get(f"{_VK}/photos.saveWallPhoto", params={
            "access_token": VK_USER_TOKEN,
            "group_id": VK_GROUP_ID,
            "photo": upload_data["photo"],
            "server": upload_data["server"],
            "hash": upload_data["hash"],
            "v": _VER,
        })
        resp = r.json()
        if "error" in resp:
            print(f"  saveWallPhoto: {resp['error']['error_msg']}")
            return None
        saved = resp["response"][0]
        return f"photo{saved['owner_id']}_{saved['id']}"


async def delete_post(post_id: int) -> bool:
    async with httpx.AsyncClient(timeout=15, trust_env=False) as c:
        r = await c.post(f"{_VK}/wall.delete", data={
            "access_token": VK_USER_TOKEN,
            "owner_id": f"-{VK_GROUP_ID}",
            "post_id": post_id,
            "v": _VER,
        })
        resp = r.json()
        if "error" in resp:
            print(f"  wall.delete: {resp['error']['error_msg']}")
            return False
        return True


async def repost_with_photo(text: str, attachment: str) -> str | None:
    async with httpx.AsyncClient(timeout=20, trust_env=False) as c:
        r = await c.post(f"{_VK}/wall.post", data={
            "access_token": VK_TOKEN,
            "owner_id": f"-{VK_GROUP_ID}",
            "message": text,
            "attachments": attachment,
            "from_group": 1,
            "v": _VER,
        })
        resp = r.json()
        if "error" in resp:
            print(f"  wall.post: {resp['error']['error_msg']}")
            return None
        return str(resp["response"]["post_id"])


async def run(dry_run: bool) -> None:
    posts = await get_posts_without_photo()
    if not posts:
        print("Все посты уже с фото.")
        return

    print(f"Постов без фото: {len(posts)}\n")

    for p in posts:
        post_id = p["id"]
        text = p.get("text", "")
        preview = text[:70].replace("\n", " ")
        print(f"#{post_id}: {preview}...")

        if dry_run:
            print("  [dry-run] пропускаем\n")
            continue

        print("  Генерирую фото...")
        photo = await generate_image(text)
        if not photo:
            print("  Фото не сгенерировано — пропускаем\n")
            continue

        print(f"  Загружаю в VK ({len(photo)} байт)...")
        attachment = await upload_photo(photo)
        if not attachment:
            print("  Загрузка не удалась — пропускаем\n")
            continue

        print(f"  Удаляю пост #{post_id}...")
        deleted = await delete_post(post_id)
        if not deleted:
            print("  Не удалось удалить — пропускаем\n")
            continue

        print("  Публикую заново с фото...")
        new_id = await repost_with_photo(text, attachment)
        if new_id:
            print(f"  ✅ Готово: vk.com/wall-{VK_GROUP_ID}_{new_id}\n")
        else:
            print("  ❌ Ошибка публикации\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
