import os

from dotenv import load_dotenv

load_dotenv()

load_dotenv()

_raw_token = (os.environ.get("BOT_TOKEN") or os.environ.get("BOT_API_KEY") or "").strip()
if not _raw_token or _raw_token == "your_bot_token_here":
    raise RuntimeError(
        "Укажите BOT_TOKEN в файле .env\n"
        "Пример: BOT_TOKEN=1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    )
token = _raw_token

WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "6090"))
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://my.cloudtelegram.ru")

TELEGRAM_PROXY = (os.environ.get("TELEGRAM_PROXY") or "").strip() or None
TELEGRAM_TIMEOUT = int(os.environ.get("TELEGRAM_TIMEOUT", "120"))
