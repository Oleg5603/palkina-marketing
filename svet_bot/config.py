import os
from dotenv import load_dotenv

load_dotenv()


class _Settings:
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    VK_TOKEN: str = os.getenv("VK_TOKEN", "")
    VK_GROUP_ID: str = os.getenv("VK_GROUP_ID", "")
    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    GIGACHAT_CREDENTIALS: str = os.getenv("GIGACHAT_CREDENTIALS", "")

    @property
    def ALLOWED_USER_IDS(self) -> list[int]:
        raw = os.getenv("ALLOWED_USER_IDS", "")
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]


settings = _Settings()
