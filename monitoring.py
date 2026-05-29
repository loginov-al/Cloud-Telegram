"""Мониторинг системы и алерты админу в Telegram."""

import asyncio
import logging
import os
import shutil
import time
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, Any

import config

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

START_TIME = time.time()
_bot: Bot | None = None
_events: deque[dict[str, Any]] = deque(maxlen=200)
_last_alerts: dict[str, float] = {}
_telegram_ok = True
_telegram_errors = 0


def init(bot: "Bot") -> None:
    global _bot
    _bot = bot


def log_event(message: str, level: str = "info") -> None:
    entry = {
        "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "level": level,
        "message": message,
    }
    _events.appendleft(entry)
    logger.log(
        logging.ERROR if level == "error" else logging.WARNING if level == "warn" else logging.INFO,
        "[event] %s",
        message,
    )


def set_telegram_status(ok: bool, error: str | None = None) -> None:
    global _telegram_ok, _telegram_errors
    was_ok = _telegram_ok
    _telegram_ok = ok
    if ok:
        if not was_ok and _telegram_errors:
            _telegram_errors = 0
            asyncio.create_task(alert("✅ Telegram снова доступен", level="info", key="tg_ok"))
    else:
        _telegram_errors += 1
        if _telegram_errors == 1 or _telegram_errors % 5 == 0:
            asyncio.create_task(
                alert(f"❌ Telegram недоступен (#{_telegram_errors}): {error or 'unknown'}", level="error", key="tg_down")
            )


def _disk_stats(path: str = "/") -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    percent = int(usage.used * 100 / usage.total) if usage.total else 0
    return {
        "total": usage.total,
        "used": usage.used,
        "free": usage.free,
        "percent": percent,
    }


def _memory_stats() -> dict[str, Any]:
    try:
        mem: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                mem[key.strip()] = int(value.strip().split()[0])
        total = mem.get("MemTotal", 0) * 1024
        avail = mem.get("MemAvailable", mem.get("MemFree", 0)) * 1024
        used = max(total - avail, 0)
        percent = int(used * 100 / total) if total else 0
        return {"total": total, "used": used, "free": avail, "percent": percent}
    except OSError:
        return {"total": 0, "used": 0, "free": 0, "percent": 0}


def _load_avg() -> tuple[float, float, float]:
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


def get_system_stats() -> dict[str, Any]:
    import storage

    uptime_sec = int(time.time() - START_TIME)
    hours, rem = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    disk = _disk_stats()
    mem = _memory_stats()
    load = _load_avg()

    users = len(storage.USER_FILES)
    files = sum(len(f) for f in storage.USER_FILES.values())
    links = len(storage.PUBLIC_LINKS)
    total_storage = sum(storage.get_used_storage(uid) for uid in storage.USER_FILES)
    sessions = len(storage.WEB_SESSIONS)

    data_dir = storage.DATA_DIR
    data_size = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file()) if data_dir.exists() else 0

    return {
        "uptime": f"{hours}ч {minutes}м {seconds}с",
        "uptime_sec": uptime_sec,
        "disk": disk,
        "memory": mem,
        "load": {"1m": round(load[0], 2), "5m": round(load[1], 2), "15m": round(load[2], 2)},
        "telegram_ok": _telegram_ok,
        "telegram_errors": _telegram_errors,
        "users": users,
        "files": files,
        "links": links,
        "sessions": sessions,
        "storage_used": total_storage,
        "storage_used_fmt": storage.format_size(total_storage),
        "data_dir_size": data_size,
        "data_dir_size_fmt": storage.format_size(data_size),
        "proxy": bool(config.TELEGRAM_PROXY),
        "web_url": config.WEB_BASE_URL,
        "bot_username": config.BOT_USERNAME,
        "admin_count": len(config.ADMIN_USER_IDS),
    }


def get_events(limit: int = 50) -> list[dict[str, Any]]:
    return list(_events)[:limit]


async def alert(message: str, level: str = "info", key: str | None = None) -> bool:
    """Отправить алерт всем админам в Telegram."""
    log_event(message, level)

    if not config.ADMIN_USER_IDS:
        return False
    if not _bot:
        return False

    if key:
        now = time.time()
        last = _last_alerts.get(key, 0)
        if now - last < config.ALERT_COOLDOWN_SEC:
            return False
        _last_alerts[key] = now

    prefix = {"info": "ℹ️", "warn": "⚠️", "error": "🚨"}.get(level, "📢")
    text = f"{prefix} <b>Облачный — алерт</b>\n\n{message}"

    sent = False
    for admin_id in config.ADMIN_USER_IDS:
        try:
            await _bot.send_message(admin_id, text, parse_mode="HTML")
            sent = True
        except Exception as exc:
            logger.error("Не удалось отправить алерт admin %s: %s", admin_id, exc)
    return sent


async def send_admin_message(text: str) -> int:
    """Отправить произвольное сообщение всем админам. Возвращает число доставленных."""
    if not _bot or not config.ADMIN_USER_IDS:
        return 0
    count = 0
    for admin_id in config.ADMIN_USER_IDS:
        try:
            await _bot.send_message(admin_id, text, parse_mode="HTML")
            count += 1
        except Exception as exc:
            logger.error("send_admin_message %s: %s", admin_id, exc)
    log_event(f"Админ-сообщение отправлено ({count} получ.)", "info")
    return count


async def health_loop() -> None:
    """Фоновая проверка ресурсов."""
    await asyncio.sleep(60)
    while True:
        try:
            stats = get_system_stats()
            disk_pct = stats["disk"]["percent"]
            mem_pct = stats["memory"]["percent"]

            if disk_pct >= config.ALERT_DISK_PERCENT:
                await alert(
                    f"Диск заполнен на <b>{disk_pct}%</b>\n"
                    f"Свободно: {stats['disk']['free'] // (1024**3)} GB",
                    level="warn",
                    key="disk_high",
                )
            if mem_pct >= config.ALERT_MEMORY_PERCENT:
                await alert(
                    f"Память занята на <b>{mem_pct}%</b>",
                    level="warn",
                    key="mem_high",
                )
        except Exception as exc:
            logger.exception("health_loop: %s", exc)
        await asyncio.sleep(config.HEALTH_CHECK_INTERVAL)
