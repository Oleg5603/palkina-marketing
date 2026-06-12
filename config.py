import os

# Credentials — берём из переменных окружения, не из кода
# Создай файл .env (по образцу .env.example) и запусти: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен — берём из системного окружения

YANDEX_LOGIN = os.getenv("YANDEX_LOGIN", "")
YANDEX_PASSWORD = os.getenv("YANDEX_PASSWORD", "")

# Токен Яндекс Директ API — рекомендуемый режим (быстрее, в рамках ToS)
# Получить: https://oauth.yandex.ru → создать приложение → scope: direct:api
YANDEX_DIRECT_TOKEN = os.getenv("YANDEX_DIRECT_TOKEN", "")

REGION_ID = 225  # Россия (213 = Москва, 2 = Санкт-Петербург)

OUTPUT_DIR = "output"
COOKIES_FILE = "output/.yandex_session.json"  # кэш сессии — не логинимся каждый раз

SEED_KEYWORDS = [
    "семейный психолог",
    "психолог для пар",
    "психотерапевт отношения",
    "кризис в браке",
    "муж изменил что делать",
    "как сохранить брак",
    "развод не хочу",
    "потеря близости в отношениях",
    "нет доверия в браке",
    "конфликты в семье помощь",
    "супружеская терапия",
    "онлайн консультация психолог отношения",
    "как примириться после ссоры",
    "психолог онлайн пара",
]

MIN_FREQUENCY = 50

# Задержка между запросами (секунды) — снижает вероятность бана
REQUEST_DELAY = 3.0
