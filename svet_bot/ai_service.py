import base64
import logging
import httpx
from config import settings

log = logging.getLogger("ai")

_SYSTEM = """Ты — помощник психотерапевта Светланы Палкиной, которая специализируется
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


async def generate_post_text(topic: str) -> str:
    if settings.GIGACHAT_CREDENTIALS:
        text = await _gigachat(topic)
        if text:
            return text

    if settings.CLAUDE_API_KEY:
        text = await _claude(topic)
        if text:
            return text

    return _placeholder(topic)


# ── GigaChat ──────────────────────────────────────────────────────────────────

async def _gigachat(topic: str) -> str | None:
    try:
        token = await _gigachat_token()
        if not token:
            return None

        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.post(
                "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "model": "GigaChat",
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": f"Напиши пост на тему: {topic}"},
                    ],
                    "max_tokens": 900,
                    "temperature": 0.8,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.error("GigaChat error: %s", exc)
        return None


async def _gigachat_token() -> str | None:
    creds = settings.GIGACHAT_CREDENTIALS
    if not creds:
        return None
    try:
        import uuid
        # Сбер выдаёт уже готовый base64-ключ — используем напрямую
        try:
            base64.b64decode(creds)
            encoded = creds
        except Exception:
            encoded = base64.b64encode(creds.encode()).decode()

        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.post(
                "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={
                    "Authorization": f"Basic {encoded}",
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


# ── Claude ────────────────────────────────────────────────────────────────────

async def _claude(topic: str) -> str | None:
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Напиши пост на тему: {topic}"}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("Claude error: %s", exc)
        return None


# ── Заглушка ──────────────────────────────────────────────────────────────────

def _placeholder(topic: str) -> str:
    return (
        f"📝 Тема: {topic}\n\n"
        "Генерация не настроена.\n\n"
        "Добавьте в svet_bot/.env один из ключей:\n"
        "• GIGACHAT_CREDENTIALS=ClientID:Secret\n"
        "• CLAUDE_API_KEY=sk-ant-...\n\n"
        "Если откликается — напишите мне."
    )
