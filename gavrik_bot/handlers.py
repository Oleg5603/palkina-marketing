import logging
import subprocess
import asyncio
import sys
import aiohttp
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    VK_TOKEN, VK_GROUP_ID, SITE_URL,
    CONTENT_PLAN_PATH, DIRECT_CSV_PATH, LANDING_DIR, ALLOWED_USER_IDS,
    VPS_HOST, VPS_USER, VPS_PASSWORD, CLAUDE_BIN
)

log = logging.getLogger(__name__)
router = Router()

# Пользователи в режиме агента
_agent_mode: set[int] = set()
# История разговора: chat_id -> [(role, text), ...]
_history: dict[int, list] = {}

# Хранилище chat_id для уведомлений (в памяти, при перезапуске сбрасывается)
_notify_chats: set[int] = set()

STAGES = [
    ("1", "Лендинг", "✅", "palkina-therapy.ru запущен, Метрика, цели"),
    ("2", "Яндекс.Директ", "⏸", "CSV готов — ждёт бюджета"),
    ("3", "ВКонтакте", "🔄", "Группа misemia, контент-план 12 постов, svet_bot"),
    ("4", "Парсинг аудитории ВК", "⏳", "Похожая аудитория — не начат"),
    ("5", "Telegram svet_bot", "⚠️", "Код готов — нужен токен @LanaS777Bot"),
    ("6", "Яндекс Метрика", "✅", "Счётчик 109801157, цель form_submit"),
    ("7", "Прогрев контент", "⏳", "Серия прогревающих постов — не начат"),
    ("8", "A/B тесты", "⏳", "Оптимизация — не начат"),
]

TASKS = [
    ("svet_bot TELEGRAM_TOKEN", "Получить: @BotFather → /mybots → @LanaS777Bot → API Token"),
    ("svet_bot ALLOWED_USER_IDS", "Написать @userinfobot — узнать Telegram ID Светланы"),
    ("Фото на сайт", "Выбрать из G:\\ФОТО\\Света → скопировать как landing/photo.jpg → залить на Beget"),
    ("Отзывы на сайт", "Заменить 5 заглушек в index.html реальными отзывами Светланы"),
    ("Запустить svet_bot", "В папке semantic_scout: python svet_bot/bot.py"),
    ("ВК посты", "Публиковать по плану: пн 10:00, ср 12:00, пт 18:00"),
    ("Яндекс.Директ", "Загрузить output/direct_campaign.csv при наличии бюджета"),
    ("Парсинг аудитории ВК", "Этап 4"),
    ("Прогрев контент", "Этап 7 — серия прогревающих постов"),
]

VK_POSTS = [
    ("1 (Пн, нед.1)", "Знакомство", "Кто я и почему работаю именно с парами"),
    ("2 (Ср, нед.1)", "Полезное", "Почему пары откладывают обращение к психологу"),
    ("3 (Пт, нед.1)", "Миф", "Миф: к психологу идут только когда совсем плохо"),
    ("4 (Пн, нед.2)", "История", "Как вышли из двухлетней холодности"),
    ("5 (Ср, нед.2)", "Практика", "3 признака, что кризис в браке — не конец"),
    ("6 (Пт, нед.2)", "Вопрос-ответ", "Можно ли прийти на сессию одному, без партнёра?"),
    ("7 (Пн, нед.3)", "Измена", "5 вопросов до решения об измене"),
    ("8 (Ср, нед.3)", "Онлайн", "Онлайн-терапия vs очная — что выбрать паре"),
    ("9 (Пт, нед.3)", "Конфликты", "Почему «просто поговорить» не работает"),
    ("10 (Пн, нед.4)", "Запись", "Что происходит на первой сессии"),
    ("11 (Ср, нед.4)", "Цена", "Стоимость сессии vs стоимость развода"),
    ("12 (Пт, нед.4)", "Близость", "Можно ли вернуть эмоциональную близость"),
]


def _auth(message: Message) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return message.from_user.id in ALLOWED_USER_IDS


def _main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Этапы", callback_data="stages")
    kb.button(text="🌐 Сайт", callback_data="site")
    kb.button(text="📱 ВК", callback_data="vk")
    kb.button(text="📅 Контент-план", callback_data="plan")
    kb.button(text="✅ Задачи", callback_data="tasks")
    kb.button(text="🚀 Управление", callback_data="manage")
    kb.button(text="🤖 Агент", callback_data="agent_mode")
    kb.adjust(2)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not _auth(message):
        return
    _notify_chats.add(message.chat.id)
    await message.answer(
        "*Гаврик* — центр управления проектом Светланы Палкиной\n\n"
        "Выбери раздел:",
        reply_markup=_main_kb()
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if not _auth(message):
        return
    await message.answer("Главное меню:", reply_markup=_main_kb())


# ───── ЭТАПЫ ─────

@router.message(Command("stages"))
async def cmd_stages(message: Message):
    if not _auth(message):
        return
    await _send_stages(message)


@router.callback_query(F.data == "stages")
async def cb_stages(callback: CallbackQuery):
    await _send_stages(callback.message)
    await callback.answer()


async def _send_stages(message: Message):
    lines = ["Этапы проекта palkina-therapy.ru\n"]
    for num, name, icon, desc in STAGES:
        lines.append(f"{icon} Этап {num}: {name}\n   {desc}\n")
    await message.answer("\n".join(lines), parse_mode=None)


# ───── САЙТ ─────

@router.message(Command("site"))
async def cmd_site(message: Message):
    if not _auth(message):
        return
    await _send_site(message)


@router.callback_query(F.data == "site")
async def cb_site(callback: CallbackQuery):
    await _send_site(callback.message)
    await callback.answer()


async def _send_site(message: Message):
    wait = await message.answer("Проверяю сайт...")
    ok = await _check_site()
    landing_files = sorted(f.name for f in LANDING_DIR.iterdir()) if LANDING_DIR.exists() else []
    text = (
        f"{'✅ Сайт работает' if ok else '❌ Сайт недоступен'}\n\n"
        f"*URL:* {SITE_URL}\n"
        f"*Хостинг:* Beget (ogp56bkn)\n"
        f"*Метрика:* 109801157\n"
        f"*Цель:* form\\_submit\n"
        f"*Calendly:* https://calendly.com/palkinoleg\n\n"
        f"*Файлы лендинга:*\n"
        + "\n".join(f"  • {f}" for f in landing_files)
    )
    await wait.delete()
    await message.answer(text)


# ───── ВКОНТАКТЕ ─────

@router.message(Command("vk"))
async def cmd_vk(message: Message):
    if not _auth(message):
        return
    await _send_vk(message)


@router.callback_query(F.data == "vk")
async def cb_vk(callback: CallbackQuery):
    await _send_vk(callback.message)
    await callback.answer()


async def _send_vk(message: Message):
    wait = await message.answer("Запрашиваю данные ВК...")
    info = await _get_vk_stats()
    await wait.delete()
    if info:
        text = (
            f"*ВКонтакте — misemia*\n\n"
            f"Подписчиков: *{info.get('members_count', '?')}*\n"
            f"Название: {info.get('name', '?')}\n"
            f"Статус: {info.get('status', '—') or '—'}\n\n"
            f"Группа: vk.com/misemia\n"
            f"Бот: @LanaS777Bot\n\n"
            f"*Расписание постов:*\n"
            f"  Пн 10:00 · Ср 12:00 · Пт 18:00\n\n"
            f"Чтобы создать пост: /newpost"
        )
    else:
        text = "❓ Нет данных ВК — проверь VK\\_TOKEN в .env"
    await message.answer(text)


# ───── КОНТЕНТ-ПЛАН ─────

@router.message(Command("plan"))
async def cmd_plan(message: Message):
    if not _auth(message):
        return
    await _send_plan(message)


@router.callback_query(F.data == "plan")
async def cb_plan(callback: CallbackQuery):
    await _send_plan(callback.message)
    await callback.answer()


async def _send_plan(message: Message):
    lines = ["*Контент-план ВКонтакте (12 постов, 4 недели)*\n"]
    for num, day_week, topic, title in VK_POSTS:
        lines.append(f"*{num}* — {topic}: {title}")
    lines.append("\n📄 Полный план: vk\\_content/content\\_plan.md")
    lines.append("Создать пост: /newpost")
    await message.answer("\n".join(lines))


# ───── ЗАДАЧИ ─────

@router.message(Command("tasks"))
async def cmd_tasks(message: Message):
    if not _auth(message):
        return
    await _send_tasks(message)


@router.callback_query(F.data == "tasks")
async def cb_tasks(callback: CallbackQuery):
    await _send_tasks(callback.message)
    await callback.answer()


async def _send_tasks(message: Message):
    lines = [f"Открытые задачи ({len(TASKS)})\n"]
    for i, (name, desc) in enumerate(TASKS, 1):
        lines.append(f"{i}. {name}\n   {desc}\n")
    await message.answer("\n".join(lines), parse_mode=None)


# ───── УПРАВЛЕНИЕ ─────

@router.message(Command("manage"))
async def cmd_manage(message: Message):
    if not _auth(message):
        return
    await _send_manage(message)


@router.callback_query(F.data == "manage")
async def cb_manage(callback: CallbackQuery):
    await _send_manage(callback.message)
    await callback.answer()


async def _send_manage(message: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Проверить сайт", callback_data="site")
    kb.button(text="📱 Статистика ВК", callback_data="vk")
    kb.button(text="✍️ Создать пост ВК", callback_data="newpost_menu")
    kb.button(text="📊 Все этапы", callback_data="stages")
    kb.button(text="✅ Задачи", callback_data="tasks")
    kb.adjust(2)
    text = (
        "*Управление проектом*\n\n"
        "Доступные команды:\n"
        "/site — проверить сайт\n"
        "/vk — статистика ВКонтакте\n"
        "/newpost — создать пост в ВК\n"
        "/stages — статус всех этапов\n"
        "/tasks — список задач\n"
        "/notify on|off — вкл/выкл уведомления\n"
        "/status — краткий статус всех проектов"
    )
    await message.answer(text, reply_markup=kb.as_markup())


# ───── НОВЫЙ ПОСТ ─────

@router.message(Command("newpost"))
async def cmd_newpost(message: Message):
    if not _auth(message):
        return
    await _send_newpost_menu(message)


@router.callback_query(F.data == "newpost_menu")
async def cb_newpost_menu(callback: CallbackQuery):
    await _send_newpost_menu(callback.message)
    await callback.answer()


async def _send_newpost_menu(message: Message):
    kb = InlineKeyboardBuilder()
    for i, (num, day_week, topic, title) in enumerate(VK_POSTS):
        kb.button(text=f"Пост {num}: {topic}", callback_data=f"post_{i}")
    kb.adjust(2)
    await message.answer(
        "*Выбери пост из плана для публикации:*\n\n"
        "Гаврик покажет текст — ты его правишь и публикуешь через svet\\_bot\n"
        "или вручную на vk.com/misemia",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("post_"))
async def cb_post_detail(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    num, day_week, topic, title = VK_POSTS[idx]
    post_texts = _get_post_template(idx)
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Скопировать текст поста", callback_data=f"copy_{idx}")
    kb.button(text="🔙 Назад к плану", callback_data="plan")
    kb.adjust(1)
    await callback.message.answer(
        f"*Пост {num} — {topic}*\n"
        f"_{title}_\n\n"
        f"{post_texts}",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("copy_"))
async def cb_copy_post(callback: CallbackQuery):
    idx = int(callback.data.split("_")[1])
    num, day_week, topic, title = VK_POSTS[idx]
    text = _get_post_template(idx)
    await callback.message.answer(
        f"Готово к копированию:\n\n{text}",
    )
    await callback.answer("Текст отправлен")


# ───── СТАТУС ─────

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not _auth(message):
        return
    wait = await message.answer("Проверяю...")
    site_ok = await _check_site()
    vk_info = await _get_vk_stats()
    await wait.delete()

    svet_ok = _check_env_key("svet_bot/.env", "TELEGRAM_TOKEN")
    direct_ok = DIRECT_CSV_PATH.exists()

    lines = [
        "*Статус проектов*\n",
        f"{'✅' if site_ok else '❌'} Сайт {SITE_URL}",
        f"{'✅' if vk_info else '❓'} ВК misemia — {vk_info.get('members_count', '?') if vk_info else '?'} подписчиков",
        f"{'✅' if svet_ok else '⚠️'} svet_bot — {'токен задан' if svet_ok else 'нужен токен'}",
        f"{'✅' if direct_ok else '⏸'} Яндекс.Директ — {'CSV готов' if direct_ok else 'ждёт бюджета'}",
        f"\n📊 /stages — подробно по этапам",
        f"✅ /tasks — {len(TASKS)} задач открыто",
    ]
    await message.answer("\n".join(lines))


# ───── УВЕДОМЛЕНИЯ ─────

@router.message(Command("notify"))
async def cmd_notify(message: Message):
    if not _auth(message):
        return
    parts = message.text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    if arg == "on":
        _notify_chats.add(message.chat.id)
        await message.answer("✅ Уведомления включены.\nТы будешь получать сигналы о новых заявках и публикациях.")
    elif arg == "off":
        _notify_chats.discard(message.chat.id)
        await message.answer("🔕 Уведомления отключены.")
    else:
        status = "включены ✅" if message.chat.id in _notify_chats else "отключены 🔕"
        await message.answer(
            f"Уведомления сейчас: *{status}*\n\n"
            "/notify on — включить\n"
            "/notify off — отключить"
        )


async def send_notification(bot, text: str):
    """Вызвать извне для отправки уведомлений во все подписанные чаты."""
    for chat_id in list(_notify_chats):
        try:
            await bot.send_message(chat_id, f"🔔 {text}")
        except Exception as e:
            log.warning("Не удалось отправить уведомление в %s: %s", chat_id, e)


# ───── ПОМОЩЬ ─────

@router.message(Command("help"))
async def cmd_help(message: Message):
    if not _auth(message):
        return
    await message.answer(
        "*Команды Гаврика*\n\n"
        "/start — главное меню\n"
        "/status — краткий статус всех проектов\n"
        "/stages — этапы (1–8) с иконками\n"
        "/site — проверить сайт\n"
        "/vk — статистика ВКонтакте\n"
        "/plan — контент-план (12 постов)\n"
        "/newpost — создать пост из плана\n"
        "/tasks — открытые задачи\n"
        "/manage — панель управления\n"
        "/notify on|off — уведомления\n"
        "/help — эта справка"
    )


# ───── АГЕНТ ─────

@router.callback_query(F.data == "agent_mode")
async def cb_agent_mode(callback: CallbackQuery):
    _agent_mode.add(callback.message.chat.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Выйти из режима агента", callback_data="agent_exit")
    kb.button(text="🗑 Очистить историю", callback_data="agent_clear")
    kb.adjust(1)
    vps_info = f"VPS: {VPS_HOST}" if VPS_HOST else "Локально (claude на этом ПК)"
    await callback.message.answer(
        "🤖 *Режим агента активен*\n\n"
        f"Соединение: `{vps_info}`\n\n"
        "Просто напишите задачу — я передам агенту и верну ответ.\n\n"
        "_Для выхода нажмите кнопку или /menu_",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "agent_exit")
async def cb_agent_exit(callback: CallbackQuery):
    _agent_mode.discard(callback.message.chat.id)
    await callback.message.answer("Вышел из режима агента.", reply_markup=_main_kb())
    await callback.answer()

@router.callback_query(F.data == "agent_clear")
async def cb_agent_clear(callback: CallbackQuery):
    _history.pop(callback.message.chat.id, None)
    await callback.message.answer("🗑 История разговора очищена.")
    await callback.answer()


@router.message(Command("agent"))
async def cmd_agent(message: Message):
    if not _auth(message):
        return
    _agent_mode.add(message.chat.id)
    vps_info = f"VPS: {VPS_HOST}" if VPS_HOST else "Локально"
    await message.answer(
        f"🤖 Режим агента включён ({vps_info})\n"
        "Пишите задачу. /menu — вернуться в меню."
    )


async def _run_claude_local(prompt: str) -> str:
    """Запуск claude локально через subprocess."""
    proc = await asyncio.create_subprocess_exec(
        CLAUDE_BIN, "--print", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        result = stdout.decode("utf-8", errors="replace").strip()
        if not result and stderr:
            result = stderr.decode("utf-8", errors="replace").strip()
        return result or "Агент не вернул ответ."
    except asyncio.TimeoutError:
        proc.kill()
        return "⏱ Таймаут — агент думал дольше 2 минут."


def _read_vps_file(client, path: str) -> str:
    """Читает файл с VPS, возвращает пустую строку если не найден."""
    try:
        _, out, _ = client.exec_command(f"cat {path} 2>/dev/null")
        return out.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""

def _run_claude_vps_sync(full_prompt: str) -> str:
    """Синхронный SSH-вызов claude на VPS (запускается в thread pool)."""
    try:
        import paramiko
    except ImportError:
        return "❌ Установите paramiko: pip install paramiko"

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        stdin, stdout, _ = client.exec_command(
            "cd /root/telegram-bot && claude --print 2>&1", timeout=120
        )
        stdin.write(full_prompt + "\n")
        stdin.channel.shutdown_write()
        stdout.channel.recv_exit_status()
        result = stdout.read().decode("utf-8", errors="replace").strip()
        client.close()
        return result or "Агент не вернул ответ."
    except Exception as e:
        return f"❌ Ошибка VPS: {e}"

def _build_prompt(chat_id: int, user_message: str) -> str:
    """Собирает полный промпт: память + история + новое сообщение."""
    import json as _json
    soul = memory = goals = ""
    saved_history = []

    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        soul   = _read_vps_file(client, "/root/telegram-bot/SOUL.md")
        memory = _read_vps_file(client, "/root/telegram-bot/MEMORY.md")
        goals  = _read_vps_file(client, "/root/telegram-bot/GOALS.md")
        # Читаем сохранённую историю из memory.json по chat_id
        raw_mem = _read_vps_file(client, "/root/telegram-bot/memory.json")
        if raw_mem:
            mem_data = _json.loads(raw_mem)
            saved_history = mem_data.get(str(chat_id), [])
        client.close()
    except Exception:
        pass

    parts = []
    if soul:
        parts.append(f"=== КТО ТЫ (SOUL.md) ===\n{soul}")
    if memory:
        parts.append(f"=== ДОЛГОСРОЧНАЯ ПАМЯТЬ (MEMORY.md) ===\n{memory}")
    if goals:
        parts.append(f"=== ЦЕЛИ (GOALS.md) ===\n{goals}")

    # Последние 10 сообщений из сохранённой истории VPS
    if saved_history:
        last = saved_history[-20:]
        hist_text = "\n".join(
            f"{'Пользователь' if m['role'] == 'user' else 'Агент'}: {m['content'][:300]}"
            for m in last
        )
        parts.append(f"=== ИСТОРИЯ ПРЕДЫДУЩИХ РАЗГОВОРОВ ===\n{hist_text}")

    # Текущая сессия (в памяти бота)
    session = _history.get(chat_id, [])
    if session:
        sess_text = "\n".join(
            f"{'Пользователь' if r == 'user' else 'Агент'}: {t}"
            for r, t in session[-12:]
        )
        parts.append(f"=== ТЕКУЩАЯ СЕССИЯ ===\n{sess_text}")

    parts.append(f"=== НОВОЕ СООБЩЕНИЕ ===\n{user_message}")
    return "\n\n".join(parts)

def _save_to_vps_memory(chat_id: int, user_msg: str, assistant_msg: str):
    """Дописывает обмен в memory.json на VPS."""
    import json as _json
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
        raw = _read_vps_file(client, "/root/telegram-bot/memory.json")
        data = _json.loads(raw) if raw else {}
        key = str(chat_id)
        if key not in data:
            data[key] = []
        data[key].append({"role": "user",      "content": user_msg})
        data[key].append({"role": "assistant",  "content": assistant_msg[:800]})
        if len(data[key]) > 100:
            data[key] = data[key][-100:]
        new_json = _json.dumps(data, ensure_ascii=False, indent=2)
        stdin, stdout, _ = client.exec_command("cat > /root/telegram-bot/memory.json")
        stdin.write(new_json)
        stdin.channel.shutdown_write()
        stdout.channel.recv_exit_status()
        client.close()
    except Exception:
        pass

async def _run_claude_vps(chat_id: int, prompt: str) -> str:
    """Запускает SSH в отдельном потоке, не блокирует event loop."""
    full_prompt = await asyncio.get_event_loop().run_in_executor(
        None, _build_prompt, chat_id, prompt
    )
    return await asyncio.get_event_loop().run_in_executor(
        None, _run_claude_vps_sync, full_prompt
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_agent_message(message: Message):
    """Перехватывает свободный текст — если агент включён, отправляет запрос."""
    if not _auth(message):
        return
    if message.chat.id not in _agent_mode:
        return  # не в режиме агента — игнорируем

    wait = await message.answer("🤖 Думаю... (0с)")
    prompt = message.text.strip()

    # Таймер: обновляет сообщение каждые 10 сек пока агент думает
    done_event = asyncio.Event()
    async def _ticker():
        elapsed = 0
        while not done_event.is_set():
            await asyncio.sleep(10)
            if done_event.is_set():
                break
            elapsed += 10
            try:
                await wait.edit_text(f"🤖 Думаю... ({elapsed}с)")
            except Exception:
                pass
    ticker_task = asyncio.create_task(_ticker())

    try:
        if VPS_HOST and VPS_PASSWORD:
            result = await _run_claude_vps(message.chat.id, prompt)
        else:
            result = await _run_claude_local(prompt)
    finally:
        done_event.set()
        ticker_task.cancel()

    # Сохраняем в историю сессии
    hist = _history.setdefault(message.chat.id, [])
    hist.append(("user", prompt))
    hist.append(("assistant", result[:500]))
    if len(hist) > 24:
        _history[message.chat.id] = hist[-24:]

    # Сохраняем в memory.json на VPS
    if VPS_HOST and VPS_PASSWORD:
        asyncio.get_event_loop().run_in_executor(
            None, _save_to_vps_memory, message.chat.id, prompt, result
        )

    await wait.delete()

    # Разбиваем длинные ответы на части (лимит Telegram 4096 символов)
    for i in range(0, len(result), 4000):
        await message.answer(result[i:i+4000])


# ───── ВСПОМОГАТЕЛЬНЫЕ ─────

async def _check_site() -> bool:
    timeout = aiohttp.ClientTimeout(total=8)
    for url in [SITE_URL, SITE_URL.replace("https://", "http://")]:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        return True
        except Exception:
            continue
    return False


async def _get_vk_stats() -> dict | None:
    if not VK_TOKEN:
        return None
    url = "https://api.vk.com/method/groups.getById"
    params = {
        "group_ids": str(VK_GROUP_ID),
        "fields": "members_count,status,name",
        "access_token": VK_TOKEN,
        "v": "5.199",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                groups = data.get("response", {}).get("groups", [])
                return groups[0] if groups else None
    except Exception as e:
        log.warning("VK stats error: %s", e)
        return None


def _check_env_key(rel_path: str, key: str) -> bool:
    from pathlib import Path
    env_path = Path(__file__).parent.parent / rel_path
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip()
                    return bool(val)
    except Exception:
        pass
    return False


def _get_post_template(idx: int) -> str:
    templates = [
        "Меня зовут Светлана Палкина — я психотерапевт, работаю с парами.\n\nЯ выбрала именно эту специализацию, потому что отношения — это главное, что есть у людей. И то, как они складываются, определяет качество всей жизни.\n\nЯ работаю онлайн. Это значит, вы можете прийти ко мне из любого города, в удобное время, без дороги и стресса.\n\nЧто привело вас на эту страницу? Напишите в комментарии.\n\n#психотерапевт #семейнаятерапия #СветланаПалкина",
        "Знаете, почему пары приходят к психологу в последний момент?\n\n1. «Само пройдёт». Не проходит.\n2. «Ещё не всё так плохо». К моменту, когда «всё так плохо» — уходит много сил и времени.\n3. «Психолог — это слабость». Это смелость.\n\nЧем раньше прийти — тем быстрее результат и тем легче путь.\n\nУзнали себя? Поставьте ❤️\n\n#психология #отношения #семья",
        "Миф: «К психологу идут только когда совсем плохо».\n\nРеальность: пары, которые приходят на профилактику — решают проблемы за 3–5 встреч.\n\nПары, которые ждут кризиса — работают месяцами.\n\nПсихолог — это не скорая помощь. Это инструмент.\n\nА вы как считаете?\n\n#мифыопсихологии #терапия #пары",
        "Однажды ко мне пришла пара — они не разговаривали почти два года. Жили в одной квартире, вели общий быт, воспитывали ребёнка.\n\nНо как чужие.\n\nЗа 8 сессий они нашли путь обратно друг к другу.\n\nЭто не магия. Это работа.\n\nПохожая ситуация? Напишите мне.\n\n#историяпары #близость #отношения",
        "Кризис в браке — не приговор.\n\n3 признака, что ещё можно выйти:\n1. Оба хотят сохранить отношения (даже если не говорят об этом)\n2. Есть общая история — дети, воспоминания, совместное прошлое\n3. Есть хотя бы одна точка, в которой вы ещё вместе\n\nЕсли хотя бы один пункт — да, шанс есть.\n\nСохраните пост — пригодится.\n\n#кризисвбраке #семья #психолог",
        "Частый вопрос: «Можно ли прийти на сессию одному, без партнёра?»\n\nДа. Это работает.\n\nКогда партнёр отказывается идти — вы всё равно можете начать. Изменения в одном человеке меняют систему целиком.\n\nЯ работаю и с парами, и с одним партнёром.\n\nЕщё вопросы? Пишите в комментарии.\n\n#вопросыпсихологу #онлайнтерапия",
        "Если случилась измена, до того как принять решение — стоит задать себе 5 вопросов:\n\n1. Что стояло за изменой — случайность или симптом?\n2. Хочу ли я разобраться — или уже всё решено?\n3. Есть ли у нас что сохранять?\n4. Могу ли я работать над доверием?\n5. Что я хочу для себя — независимо от партнёра?\n\nЭти вопросы не дают ответов. Они дают ясность.\n\nПоделитесь с тем, кому это нужно.\n\n#измена #отношения #психолог",
        "Онлайн-терапия vs очная: что выбрать паре?\n\nОнлайн:\n✅ Любой город\n✅ Не нужно ехать вместе\n✅ Привычная обстановка снижает тревогу\n\nОчная:\n✅ Физическое присутствие\n✅ Для некоторых — ощущение «серьёзности»\n\nЯ работаю онлайн. 90% моих клиентов — это пары из разных городов.\n\nВы пробовали онлайн-сессии?\n\n#онлайнтерапия #психологонлайн",
        "Почему «просто поговорить» в конфликте не работает?\n\nПотому что в момент ссоры оба человека в режиме защиты. Слышат не слова — слышат угрозу.\n\nЧто работает:\n— Пауза (выйти из комнаты, остыть)\n— Говорить о себе: «Я чувствую...» вместо «Ты всегда...»\n— Один вопрос: «Что тебе сейчас нужно?\"\n\nПокажите партнёру.\n\n#конфликты #ссоры #семья",
        "Что происходит на первой сессии — честно.\n\nДо: волнение, «а вдруг осудят» — нормально.\n\nВо время:\n— Знакомство: кто вы, что случилось\n— Я не даю советов сразу — я слушаю\n— Мы вместе формулируем запрос\n\nПосле:\n— Ясность: что будем делать\n— Договорённость о следующем шаге\n\nПервичная сессия 60–90 мин — 5000 ₽\n\nЗаписаться: palkina-therapy.ru\n\n#перваясессия #терапия #психолог",
        "Стоимость сессии — 3000–5000 ₽.\nСтоимость развода — от 50 000 ₽ + годы на восстановление.\n\nЭто не реклама.\n\nЭто просто математика.\n\nПервичная сессия — 5000 ₽. Без предоплаты. Онлайн.\n\nЗапись в комментарии или на сайте.\n\n#стоимостьтерапии #инвестиции",
        "Можно ли вернуть близость, если её не было уже несколько лет?\n\nДа. Но это работа.\n\nЭмоциональное отчуждение — не конец. Это сигнал.\n\nЯ видела пары, которые нашли путь обратно после 5 лет холодности.\n\nЕсли чувствуете, что стали чужими — напишите мне. Разберёмся вместе.\n\n#близость #отношения #психотерапевт",
    ]
    if 0 <= idx < len(templates):
        return templates[idx]
    return "Текст поста не найден."
