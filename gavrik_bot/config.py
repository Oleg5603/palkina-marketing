import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "227082800"))
SITE_URL = os.getenv("SITE_URL", "https://palkina-therapy.ru")

# VPS агент (опционально — если не задан, claude запускается локально)
VPS_HOST = os.getenv("VPS_HOST", "")
VPS_USER = os.getenv("VPS_USER", "agent")
VPS_PASSWORD = os.getenv("VPS_PASSWORD", "")
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")

_raw_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS: list[int] = [
    int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()
]

PROJECT_ROOT = BASE_DIR.parent
CONTENT_PLAN_PATH = PROJECT_ROOT / "vk_content" / "content_plan.md"
DIRECT_CSV_PATH = PROJECT_ROOT / "output" / "direct_campaign.csv"
LANDING_DIR = PROJECT_ROOT / "landing"
