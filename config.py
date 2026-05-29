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

_raw_proxy = (os.environ.get("TELEGRAM_PROXY") or "").strip() or None
# socks5h — DNS через прокси (важно на RU-VPS, где api.telegram.org заблокирован)
if _raw_proxy and _raw_proxy.startswith("socks5://"):
    _raw_proxy = "socks5h://" + _raw_proxy[len("socks5://") :]
TELEGRAM_PROXY = _raw_proxy
TELEGRAM_TIMEOUT = int(os.environ.get("TELEGRAM_TIMEOUT", "120"))
BOT_USERNAME = (os.environ.get("BOT_USERNAME") or "RUcloud1_bot").strip().lstrip("@")

# Админ-панель и алерты
ADMIN_SECRET = (os.environ.get("ADMIN_SECRET") or "").strip()
ADMIN_USER_IDS: list[int] = [
    int(x.strip()) for x in (os.environ.get("ADMIN_USER_IDS") or "").split(",") if x.strip().isdigit()
]
ALERT_DISK_PERCENT = int(os.environ.get("ALERT_DISK_PERCENT", "85"))
ALERT_MEMORY_PERCENT = int(os.environ.get("ALERT_MEMORY_PERCENT", "90"))
ALERT_COOLDOWN_SEC = int(os.environ.get("ALERT_COOLDOWN_SEC", "900"))
HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "300"))
