#!/bin/bash
# Исправление RuntimeError: no running event loop (ProxyConnector)
set -e
cd "$(dirname "$0")/.."

python3 << 'PY'
from pathlib import Path

path = Path("bot.py")
text = path.read_text()

new_block = '''def create_bot() -> Bot:
    from aiogram.client.session.aiohttp import AiohttpSession

    session_kwargs: dict = {"timeout": config.TELEGRAM_TIMEOUT}
    if config.TELEGRAM_PROXY:
        session_kwargs["proxy"] = config.TELEGRAM_PROXY
        logger.info("Telegram через прокси: %s", config.TELEGRAM_PROXY.split("@")[-1])
    else:
        logger.warning(
            "TELEGRAM_PROXY не задан — на RU-VPS Telegram API часто заблокирован"
        )

    session = AiohttpSession(**session_kwargs)
    return Bot(token=config.token, session=session)


bot = create_bot()'''

import re
pattern = r'def create_bot\(\) -> Bot:.*?^bot = create_bot\(\)'
updated, n = re.subn(pattern, new_block, text, count=1, flags=re.MULTILINE | re.DOTALL)
if n != 1:
    raise SystemExit("Не удалось найти create_bot() в bot.py — обновите файл вручную")
path.write_text(updated)
print("OK: bot.py исправлен")
PY

systemctl restart cloudtelegram
sleep 2
journalctl -u cloudtelegram -n 20 --no-pager
