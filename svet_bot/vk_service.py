import io
import logging
import httpx
from config import settings

log = logging.getLogger("vk")

_API = "https://api.vk.com/method"
_VER = "5.199"


async def publish_to_vk(text: str, photo: io.BytesIO | None = None) -> tuple[bool, str]:
    if not settings.VK_TOKEN or not settings.VK_GROUP_ID:
        return False, (
            "VK не настроен. Добавьте в .env:\n\n"
            "VK_TOKEN=ваш_токен\n"
            "VK_GROUP_ID=id_группы (число без минуса)\n\n"
            "Как получить токен:\n"
            "1. vk.com/dev → Мои приложения → Создать приложение\n"
            "2. Тип: Standalone-приложение\n"
            "3. Настройки → Получить токен пользователя\n"
            "4. Отметьте права: Стена, Фотографии\n\n"
            "Текст поста — скопируйте вручную:"
        )

    group_id = settings.VK_GROUP_ID.lstrip("-")
    owner_id = f"-{group_id}"
    token = settings.VK_TOKEN

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            attachment = ""

            if photo is not None:
                # 1. Получаем URL для загрузки фото
                r = await client.get(f"{_API}/photos.getWallUploadServer", params={
                    "access_token": token,
                    "group_id": group_id,
                    "v": _VER,
                })
                r.raise_for_status()
                resp = r.json()
                if "error" in resp:
                    return False, f"VK API: {resp['error']['error_msg']}"
                upload_url = resp["response"]["upload_url"]

                # 2. Загружаем фото
                photo.seek(0)
                r = await client.post(
                    upload_url,
                    files={"photo": ("photo.jpg", photo, "image/jpeg")},
                )
                r.raise_for_status()
                upload_data = r.json()

                # 3. Сохраняем фото в альбоме
                r = await client.get(f"{_API}/photos.saveWallPhoto", params={
                    "access_token": token,
                    "group_id": group_id,
                    "photo": upload_data["photo"],
                    "server": upload_data["server"],
                    "hash": upload_data["hash"],
                    "v": _VER,
                })
                r.raise_for_status()
                resp = r.json()
                if "error" in resp:
                    return False, f"VK saveWallPhoto: {resp['error']['error_msg']}"
                saved = resp["response"][0]
                attachment = f"photo{saved['owner_id']}_{saved['id']}"

            # 4. Публикуем пост
            params: dict = {
                "access_token": token,
                "owner_id": owner_id,
                "message": text,
                "from_group": 1,
                "v": _VER,
            }
            if attachment:
                params["attachments"] = attachment

            r = await client.get(f"{_API}/wall.post", params=params)
            r.raise_for_status()
            resp = r.json()

            if "error" in resp:
                return False, f"VK wall.post: {resp['error']['error_msg']}"

            post_id = resp["response"]["post_id"]
            url = f"https://vk.com/wall{owner_id}_{post_id}"
            return True, url

    except httpx.HTTPError as exc:
        log.error("HTTP error: %s", exc)
        return False, f"Сетевая ошибка: {exc}"
    except Exception as exc:
        log.error("VK publish error: %s", exc)
        return False, str(exc)
