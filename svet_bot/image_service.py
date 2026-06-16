import asyncio
import base64
import logging

import httpx
from config import settings

log = logging.getLogger("image")

_API = "https://api-key.fusionbrain.ai"
_STYLE = "DEFAULT"


async def generate_post_image(topic: str) -> bytes | None:
    """Генерирует картинку к посту по теме через Kandinsky (FusionBrain). None — если не настроено/не вышло."""
    if not settings.FUSIONBRAIN_API_KEY or not settings.FUSIONBRAIN_SECRET_KEY:
        return None

    headers = {
        "X-Key": f"Key {settings.FUSIONBRAIN_API_KEY}",
        "X-Secret": f"Secret {settings.FUSIONBRAIN_SECRET_KEY}",
    }
    prompt = (
        f"Тёплая, спокойная иллюстрация на тему «{topic}». "
        "Пара или человек, мягкие пастельные тона, без текста на изображении, минимализм."
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(f"{_API}/key/api/v1/pipelines", headers=headers)
            r.raise_for_status()
            pipeline_id = r.json()[0]["id"]

            params = {
                "type": "GENERATE",
                "numImages": 1,
                "width": 1024,
                "height": 1024,
                "generateParams": {"query": prompt},
            }
            files = {
                "pipeline_id": (None, pipeline_id),
                "params": (None, str(params).replace("'", '"'), "application/json"),
            }
            r = await client.post(f"{_API}/key/api/v1/pipeline/run", headers=headers, files=files)
            r.raise_for_status()
            run_uuid = r.json()["uuid"]

            for _ in range(20):
                await asyncio.sleep(3)
                r = await client.get(f"{_API}/key/api/v1/pipeline/status/{run_uuid}", headers=headers)
                r.raise_for_status()
                data = r.json()
                if data["status"] == "DONE":
                    image_b64 = data["result"]["files"][0]
                    return base64.b64decode(image_b64)
                if data["status"] == "FAIL":
                    log.warning("FusionBrain generation failed: %s", data.get("errorDescription"))
                    return None

            log.warning("FusionBrain generation timed out")
            return None

    except Exception as exc:
        log.error("FusionBrain error: %s", exc)
        return None
