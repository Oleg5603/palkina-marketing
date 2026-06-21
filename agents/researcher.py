"""
Исследователь — читает стену лида, выбирает пост с болью через GigaChat.

Вход:  qualified_leads.json  (поле status == "qualified")
Выход: enriched_leads.json   (добавляет post_id, post_owner_id, pain_tags, post_excerpt)

Запуск:
  python researcher.py
"""

import asyncio
import io
import json
import logging
import sys
import uuid
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from dotenv import dotenv_values

_ROOT  = Path(__file__).parent
_SVET  = _ROOT.parent / "svet_bot"
_ENV   = _SVET / ".env"

_QUALIFIED_FILE = _ROOT / "qualified_leads.json"
_ENRICHED_FILE  = _ROOT / "enriched_leads.json"

_env = dotenv_values(_ENV)
VK_TOKEN            = _env.get("VK_TOKEN", "")
VK_USER_TOKEN       = _env.get("VK_USER_TOKEN", "")
GIGACHAT_CREDENTIALS = _env.get("GIGACHAT_CREDENTIALS", "")

_VK_API      = "https://api.vk.com/method"
_VK_VER      = "5.199"
_GC_AUTH     = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_GC_API      = "https://gigachat.devices.sberbank.ru/api/v1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("researcher")

_SYSTEM = """Ты анализируешь посты человека ВКонтакте.
Найди пост, в котором человек пишет о проблемах в отношениях, одиночестве, разводе,
конфликтах с партнёром или поиске близости. Верни JSON:
{
  "post_index": <индекс поста в массиве, 0-based>,
  "pain_tags": ["тег1", "тег2"],
  "excerpt": "<цитата до 100 символов>"
}
Если подходящего поста нет — верни {"post_index": -1, "pain_tags": [], "excerpt": ""}"""


def load_leads(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_leads(path: Path, leads: list[dict]) -> None:
    path.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")


async def gigachat_token(client: httpx.AsyncClient) -> str | None:
    if not GIGACHAT_CREDENTIALS:
        return None
    try:
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
        log.error("GigaChat token error: %s", exc)
        return None


async def get_wall_posts(client: httpx.AsyncClient, vk_id: int) -> list[dict]:
    token = VK_USER_TOKEN or VK_TOKEN
    try:
        r = await client.get(f"{_VK_API}/wall.get", params={
            "access_token": token,
            "owner_id": vk_id,
            "count": 20,
            "filter": "owner",
            "v": _VK_VER,
        })
        r.raise_for_status()
        resp = r.json()
        if "error" in resp:
            log.warning("wall.get error для %s: %s", vk_id, resp["error"]["error_msg"])
            return []
        return resp["response"]["items"]
    except Exception as exc:
        log.error("wall.get exception: %s", exc)
        return []


async def find_pain_post(gc_token: str, posts: list[dict]) -> dict:
    texts = [
        {"index": i, "text": p.get("text", "")[:300]}
        for i, p in enumerate(posts)
        if p.get("text", "").strip()
    ]
    if not texts:
        return {"post_index": -1, "pain_tags": [], "excerpt": ""}

    prompt = f"Посты:\n{json.dumps(texts, ensure_ascii=False)}"
    try:
        async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as gc:
            r = await gc.post(
                f"{_GC_API}/chat/completions",
                headers={"Authorization": f"Bearer {gc_token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            # ищем JSON в ответе
            start = content.find("{")
            end   = content.rfind("}") + 1
            return json.loads(content[start:end])
    except Exception as exc:
        log.error("GigaChat analyze error: %s", exc)
        return {"post_index": -1, "pain_tags": [], "excerpt": ""}


async def run() -> None:
    qualified = load_leads(_QUALIFIED_FILE)
    enriched  = load_leads(_ENRICHED_FILE)
    enriched_ids = {l["vk_id"] for l in enriched}

    to_process = [l for l in qualified if l.get("status") == "qualified"
                  and l["vk_id"] not in enriched_ids]

    if not to_process:
        log.info("Нет новых лидов для исследования")
        return

    async with httpx.AsyncClient(verify=False, timeout=30, trust_env=False) as client:
        gc_token = await gigachat_token(client)
        if not gc_token:
            log.error("Нет токена GigaChat — выход")
            return

        for lead in to_process:
            vk_id = lead["vk_id"]
            log.info("Исследую лида: %s (%s)", lead.get("name", vk_id), vk_id)

            posts = await get_wall_posts(client, vk_id)
            if not posts:
                log.info("Стена закрыта или пуста: %s", vk_id)
                lead["status"] = "no_posts"
                enriched.append(lead)
                continue

            result = await find_pain_post(gc_token, posts)
            idx = result.get("post_index", -1)

            if idx < 0 or idx >= len(posts):
                log.info("Подходящего поста не найдено: %s", vk_id)
                lead["status"] = "no_pain_post"
                enriched.append(lead)
                continue

            post = posts[idx]
            lead.update({
                "status":         "researched",
                "post_id":        post["id"],
                "post_owner_id":  post["owner_id"],
                "pain_tags":      result.get("pain_tags", []),
                "post_excerpt":   result.get("excerpt", ""),
            })
            log.info("Найден пост #%s | боль: %s | цитата: %s",
                     post["id"], lead["pain_tags"], lead["post_excerpt"])
            enriched.append(lead)

    save_leads(_ENRICHED_FILE, enriched)
    log.info("Готово. Обработано лидов: %d", len(to_process))


if __name__ == "__main__":
    asyncio.run(run())
