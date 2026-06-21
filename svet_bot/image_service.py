import logging
import urllib.parse

import httpx

log = logging.getLogger("image")


async def generate_post_image(topic: str) -> bytes | None:
    """Генерирует картинку через Pollinations.ai (бесплатно, без ключей)."""
    prompt = (
        f"Cinematic photo: {topic}. "
        "Real couple or person, warm natural light, soft bokeh background, "
        "emotional and intimate mood, professional photography, no text, 4k"
    )
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        "?model=flux-realism&width=1024&height=1024&nologo=true&enhance=true"
    )

    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    except Exception as exc:
        log.error("Pollinations image error: %s", exc)
        return None
