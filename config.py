import os

from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("BOT_TOKEN") or os.environ.get("BOT_API_KEY")
if not token:
    raise RuntimeError("Укажите BOT_TOKEN в файле .env")

WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "6090"))
WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://my.cloudtelegram.ru")
