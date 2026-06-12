from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📝 Создать пост", callback_data="create_post")
    b.button(text="📋 Список тем", callback_data="show_topics")
    b.button(text="⚙️ Статус", callback_data="status")
    b.adjust(1)
    return b.as_markup()


def topics_kb(topics: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, topic in enumerate(topics):
        label = topic if len(topic) <= 40 else topic[:38] + "…"
        b.button(text=f"{i + 1}. {label}", callback_data=f"topic_{i}")
    b.button(text="✏️ Своя тема", callback_data="topic_custom")
    b.button(text="⬅️ Назад", callback_data="back_menu")
    b.adjust(1)
    return b.as_markup()


def photo_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📷 Добавлю фото", callback_data="photo_yes")
    b.button(text="🚫 Без фото", callback_data="photo_no")
    b.button(text="⬅️ Назад к темам", callback_data="back_topics")
    b.adjust(2, 1)
    return b.as_markup()


def preview_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Опубликовать в VK", callback_data="publish_vk")
    b.button(text="🔄 Переделать заново", callback_data="redo_post")
    b.button(text="✏️ Уточнить тему", callback_data="edit_note")
    b.button(text="❌ Отмена", callback_data="cancel_post")
    b.adjust(1)
    return b.as_markup()


def back_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏠 Главное меню", callback_data="back_menu")
    return b.as_markup()
