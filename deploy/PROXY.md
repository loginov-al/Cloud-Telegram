# Telegram заблокирован на RU-VPS — нужен прокси

## 1. Диагностика

```bash
cd ~/myproject/cloud
bash deploy/check-telegram.sh
```

## 2. SOCKS5 на зарубежном VPS (EU/US, ~3$/мес)

На **прокси-сервере** (не на nsk-1-vm):

```bash
apt update && apt install -y microsocks
microsocks -i 0.0.0.0 -p 1080 -u botproxy -P YourStrongPass
```

Откройте порт 1080 в файрволе прокси-сервера.

## 3. Настройка бота

На **основном сервере** (`nsk-1-vm`), файл `.env`:

```
BOT_TOKEN=ваш_токен
WEB_HOST=127.0.0.1
WEB_PORT=6090
WEB_BASE_URL=https://my.cloudtelegram.ru
TELEGRAM_PROXY=socks5://botproxy:YourStrongPass@IP_ПРОКСИ:1080
TELEGRAM_TIMEOUT=120
```

## 4. Установка aiohttp-socks и перезапуск

```bash
cd ~/myproject/cloud
.venv/bin/pip install aiohttp-socks
systemctl restart cloudtelegram
journalctl -u cloudtelegram -f
```

Должно появиться: `Telegram через прокси: IP:1080` и `Telegram подключён: @...`

## 5. Обновление кода с GitHub

```bash
cd ~/myproject/cloud
cp .env /tmp/env_backup
git pull   # или скопируйте файлы из Cloud-Telegram/
cp /tmp/env_backup .env
.venv/bin/pip install -r requirements.txt
systemctl restart cloudtelegram
```

## Важно

- Веб-панель (`https://my.cloudtelegram.ru`) работает **без** прокси
- Telegram-бот **требует** прокси на RU-хостинге
- Либо перенесите бота на VPS за рубежом — тогда прокси не нужен
