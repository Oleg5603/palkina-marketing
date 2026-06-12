import logging
from config import settings

log = logging.getLogger("ai")

_SYSTEM = """Ты — помощник психотерапевта Светланы Палкиной, которая специализируется
на супружеских и партнёрских отношениях. Пишешь посты для её страницы ВКонтакте.

Правила:
- Тёплый, доверительный тон. Без агрессии и давления.
- 200–350 слов.
- Без хэштегов и смайлов в начале абзацев.
- Структура: цепляющий первый абзац → мысль или короткая история → вывод → мягкий призыв.
- Заканчивай фразой «Если откликается — напишите мне».
- Не используй слова: экзистенциальный, нарратив, контейнировать, триггер."""


async def generate_post_text(topic: str) -> str:
    if not settings.CLAUDE_API_KEY:
        return _placeholder(topic)

    try:
        from anthropic import AsyncAnthropic  # noqa: PLC0415
    except ImportError:
        return _placeholder(topic) + "\n\n[pip install anthropic]"

    try:
        client = AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Напиши пост на тему: {topic}"}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API error: %s", exc)
        return _placeholder(topic) + f"\n\n[Ошибка генерации: {exc}]"


def _placeholder(topic: str) -> str:
    return (
        f"📝 Тема: {topic}\n\n"
        "Здесь будет текст поста, сгенерированный Claude.\n\n"
        "Чтобы включить генерацию — добавьте CLAUDE_API_KEY в файл .env:\n"
        "1. Перейдите на console.anthropic.com\n"
        "2. API Keys → Create Key\n"
        "3. Вставьте ключ в .env: CLAUDE_API_KEY=sk-ant-...\n\n"
        "Если откликается — напишите мне."
    )
