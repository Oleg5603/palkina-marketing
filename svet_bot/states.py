from aiogram.fsm.state import State, StatesGroup


class PostFlow(StatesGroup):
    choosing_topic = State()
    waiting_custom_topic = State()
    waiting_photo = State()
    showing_preview = State()
    waiting_edit_note = State()
