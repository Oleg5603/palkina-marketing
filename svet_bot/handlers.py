import json
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import settings
from states import PostFlow
from keyboards import main_menu_kb, topics_kb, photo_kb, preview_kb, back_menu_kb
from ai_service import generate_post_text
from vk_service import publish_to_vk

router = Router()
log = logging.getLogger("handlers")

_TOPICS_FILE = Path(__file__).parent / "topics.json"


def _load_topics() -> list[str]:
    if _TOPICS_FILE.exists():
        return json.loads(_TOPICS_FILE.read_text(encoding="utf-8"))
    return ["Психология отношений в паре"]


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer(
        "Привет, Светлана 👋\n\n"
        "Я Свет — помогаю создавать посты для страницы ВКонтакте.\n\n"
        "Что делаем?",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(
        "/start — главное меню\n"
        "/status — проверить настройки\n\n"
        "Для создания поста нажмите «📝 Создать пост» в меню.",
        reply_markup=main_menu_kb(),
    )


@router.message(Command("status"))
async def cmd_status(msg: Message) -> None:
    await _show_status(msg)


@router.message(Command("myid"))
async def cmd_myid(msg: Message) -> None:
    await msg.answer(f"Ваш Telegram ID: {msg.from_user.id}")


# ── Главное меню ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_menu")
async def cb_back_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "status")
async def cb_status(cb: CallbackQuery) -> None:
    await _show_status(cb.message, edit=True)
    await cb.answer()


async def _show_status(target: Message, edit: bool = False) -> None:
    vk_ok = bool(settings.VK_TOKEN and settings.VK_GROUP_ID)
    ai_ok = bool(settings.CLAUDE_API_KEY)
    text = (
        "Статус Света:\n\n"
        f"VK публикация:  {'✅ настроена' if vk_ok else '❌ не настроена'}\n"
        f"Генерация текста: {'✅ настроена' if ai_ok else '❌ не настроена'}\n"
        f"Бот:            ✅ работает\n\n"
        + ("" if vk_ok else "Добавьте VK_TOKEN и VK_GROUP_ID в .env\n")
        + ("" if ai_ok else "Добавьте CLAUDE_API_KEY в .env для генерации текста\n")
    )
    if edit:
        await target.edit_text(text.strip(), reply_markup=back_menu_kb())
    else:
        await target.answer(text.strip(), reply_markup=main_menu_kb())


# ── Список тем ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "show_topics")
async def cb_show_topics(cb: CallbackQuery) -> None:
    topics = _load_topics()
    lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    await cb.message.edit_text(
        f"Темы постов:\n\n{lines}",
        reply_markup=back_menu_kb(),
    )
    await cb.answer()


# ── Создать пост: выбор темы ───────────────────────────────────────────────────

@router.callback_query(F.data == "create_post")
async def cb_create_post(cb: CallbackQuery, state: FSMContext) -> None:
    topics = _load_topics()
    await state.set_state(PostFlow.choosing_topic)
    await cb.message.edit_text(
        "Выберите тему поста или введите свою:",
        reply_markup=topics_kb(topics),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("topic_") & ~F.data.endswith("custom"))
async def cb_topic_from_list(cb: CallbackQuery, state: FSMContext) -> None:
    idx = int(cb.data.split("_", 1)[1])
    topics = _load_topics()
    topic = topics[idx] if idx < len(topics) else topics[0]
    await state.update_data(topic=topic, photo_id=None)
    await state.set_state(PostFlow.waiting_photo)
    await cb.message.edit_text(
        f"Тема: {topic}\n\nДобавить фото к посту?",
        reply_markup=photo_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "topic_custom")
async def cb_topic_custom(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostFlow.waiting_custom_topic)
    await cb.message.edit_text(
        "Напишите тему поста:",
        reply_markup=back_menu_kb(),
    )
    await cb.answer()


@router.message(PostFlow.waiting_custom_topic, F.text)
async def msg_custom_topic(msg: Message, state: FSMContext) -> None:
    topic = msg.text.strip()
    await state.update_data(topic=topic, photo_id=None)
    await state.set_state(PostFlow.waiting_photo)
    await msg.answer(
        f"Тема: {topic}\n\nДобавить фото к посту?",
        reply_markup=photo_kb(),
    )


@router.message(PostFlow.waiting_custom_topic)
async def msg_custom_topic_wrong(msg: Message) -> None:
    await msg.answer("Напишите тему текстом.")


# ── Фото ────────────────────────────────────────────────────────────────────────

@router.callback_query(PostFlow.waiting_photo, F.data == "back_topics")
async def cb_back_topics(cb: CallbackQuery, state: FSMContext) -> None:
    topics = _load_topics()
    await state.set_state(PostFlow.choosing_topic)
    await cb.message.edit_text(
        "Выберите тему поста или введите свою:",
        reply_markup=topics_kb(topics),
    )
    await cb.answer()


@router.callback_query(PostFlow.waiting_photo, F.data == "photo_no")
async def cb_photo_no(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await _generate_and_show(cb.message, state, edit=True)


@router.callback_query(PostFlow.waiting_photo, F.data == "photo_yes")
async def cb_photo_yes(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_text(
        "Отправьте фото:",
        reply_markup=back_menu_kb(),
    )
    await cb.answer()


@router.message(PostFlow.waiting_photo, F.photo)
async def msg_photo(msg: Message, state: FSMContext) -> None:
    photo_id = msg.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await _generate_and_show(msg, state, edit=False)


@router.message(PostFlow.waiting_photo)
async def msg_photo_wrong(msg: Message) -> None:
    await msg.answer("Отправьте фото или нажмите «Без фото» выше.")


# ── Генерация и предпросмотр ───────────────────────────────────────────────────

async def _generate_and_show(target: Message, state: FSMContext, edit: bool) -> None:
    data = await state.get_data()
    topic = data.get("topic", "психология отношений")

    if edit:
        status = await target.edit_text("⏳ Генерирую текст поста…")
    else:
        status = await target.answer("⏳ Генерирую текст поста…")

    text = await generate_post_text(topic)
    await state.update_data(post_text=text)
    await state.set_state(PostFlow.showing_preview)

    preview = f"*Предпросмотр поста:*\n\n{text}\n\n——\nТема: {topic}"
    try:
        await status.edit_text(preview, reply_markup=preview_kb(), parse_mode="Markdown")
    except Exception:
        await status.edit_text(f"Предпросмотр поста:\n\n{text}\n\n——\nТема: {topic}", reply_markup=preview_kb())


# ── Действия с предпросмотром ──────────────────────────────────────────────────
# Фильтр по состоянию убран: после перезапуска бота MemoryStorage сбрасывается,
# старые клавиатуры продолжают показываться, но состояние пустое → бот молчал.

@router.callback_query(F.data == "redo_post")
async def cb_redo(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    data = await state.get_data()
    if not data.get("topic"):
        # состояние потеряно — пробуем извлечь тему из текста сообщения
        msg_text = cb.message.text or ""
        topic = _extract_topic_from_preview(msg_text) or "психология отношений"
        await state.update_data(topic=topic)
    await _generate_and_show(cb.message, state, edit=True)


@router.callback_query(F.data == "cancel_post")
async def cb_cancel(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text("Отменено.", reply_markup=main_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "edit_note")
async def cb_edit_note(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PostFlow.waiting_edit_note)
    await cb.message.edit_text(
        "Что уточнить? Напишите комментарий — перепишу с учётом:",
        reply_markup=back_menu_kb(),
    )
    await cb.answer()


@router.message(PostFlow.waiting_edit_note, F.text)
async def msg_edit_note(msg: Message, state: FSMContext) -> None:
    note = msg.text.strip()
    data = await state.get_data()
    base_topic = data.get("topic", "психология отношений")
    updated_topic = f"{base_topic}. Уточнение: {note}"
    await state.update_data(topic=updated_topic)
    await _generate_and_show(msg, state, edit=False)


def _extract_topic_from_preview(text: str) -> str:
    """Достаём тему из текста предпросмотра: строка 'Тема: ...'"""
    for line in text.splitlines():
        if line.startswith("Тема:"):
            return line.replace("Тема:", "").strip()
    return ""


def _extract_text_from_preview(text: str) -> str:
    """Достаём текст поста из предпросмотра (между заголовком и разделителем)"""
    markers = ["Предпросмотр поста:\n\n", "Предпросмотр поста:\n"]
    for marker in markers:
        if marker in text:
            body = text.split(marker, 1)[1]
            if "\n\n——" in body:
                body = body.split("\n\n——")[0]
            return body.strip()
    return text.strip()


# ── Публикация в VK ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "publish_vk")
async def cb_publish(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    raw_text = data.get("post_text", "")

    # Если состояние потеряно — берём текст прямо из сообщения
    if not raw_text and cb.message.text:
        raw_text = _extract_text_from_preview(cb.message.text)

    if not raw_text:
        await cb.answer("Текст поста не найден. Создайте пост заново.", show_alert=True)
        await cb.message.edit_text("Создайте пост заново:", reply_markup=main_menu_kb())
        return

    # Убираем Markdown-звёздочки — ВК их не поддерживает
    text = raw_text.replace("**", "").replace("*", "")
    photo_id = data.get("photo_id")

    await cb.message.edit_text("📤 Публикую в VK…")

    photo_bytes = None
    if photo_id:
        try:
            photo_bytes = await bot.download(photo_id)
        except Exception as exc:
            log.warning("Photo download failed: %s", exc)

    ok, result = await publish_to_vk(text, photo_bytes)
    await state.clear()

    if ok:
        await cb.message.edit_text(
            f"✅ Опубликовано!\n\n{result}",
            reply_markup=main_menu_kb(),
        )
    else:
        await cb.message.edit_text(
            f"❌ {result}\n\n──────\n{text}",
            reply_markup=main_menu_kb(),
        )
    await cb.answer()


# ── Catch-all ──────────────────────────────────────────────────────────────────

@router.message()
async def unknown_msg(msg: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await msg.answer("Используйте меню. /start — главное меню.")
