# Деплой на новый сервер

Один сервер = **nginx** (HTTPS) + **бот** (порт 6090). Всё на одном домене:

| URL | Что это |
|-----|---------|
| `https://ваш-домен.ru/` | Портал + веб-панель |
| `https://dev.cloudtelegram.ru/` | Документация (отдельный поддомен) |
| `https://ваш-домен.ru/admin?key=...` | Админ-панель |

В `.env`:
```env
WEB_BASE_URL=https://my.cloudtelegram.ru
DOCS_BASE_URL=https://dev.cloudtelegram.ru
```

Nginx: два `server_name` → один `proxy_pass http://127.0.0.1:6090`. Бот по заголовку `Host` показывает docs или панель.

---

## 1. Сервер

- Ubuntu 22.04 / 24.04 (EU-VPS — Telegram доступен без прокси)
- 1 GB RAM, 10+ GB диск
- Домен с A-записью на IP сервера

---

## 2. Одна команда (установка)

```bash
apt update && apt install -y git
git clone https://github.com/loginov-al/Cloud-Telegram.git /root/myproject/cloud
cd /root/myproject/cloud

export DOMAIN=my.cloudtelegram.ru   # ваш домен
bash deploy/install.sh
```

---

## 3. Настройка `.env`

```bash
nano /root/myproject/cloud/.env
```

```env
BOT_TOKEN=123456:AAH...
WEB_HOST=127.0.0.1
WEB_PORT=6090
WEB_BASE_URL=https://my.cloudtelegram.ru
BOT_USERNAME=RUcloud1_bot
TELEGRAM_TIMEOUT=120

# Админ (опционально)
ADMIN_USER_IDS=ВАШ_TELEGRAM_ID
ADMIN_SECRET=случайная_строка_32_символа
```

---

## 4. Firewall (Timeweb / облако)

Откройте **TCP 22, 80, 443**.

На сервере:
```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

---

## 5. SSL и запуск

```bash
certbot --nginx -d my.cloudtelegram.ru
systemctl start cloudtelegram
journalctl -u cloudtelegram -f
```

Ожидается: `Telegram подключён: @RUcloud1_bot`

---

## 6. Перенос со старого сервера

**На старом сервере** — остановить бота:
```bash
systemctl stop cloudtelegram
systemctl disable cloudtelegram
```

**Скопировать данные на новый:**
```bash
# на новом сервере
scp -r root@СТАРЫЙ_IP:/root/myproject/cloud/.env /root/myproject/cloud/
scp -r root@СТАРЫЙ_IP:/root/myproject/cloud/data /root/myproject/cloud/
```

**DNS** — сменить A-запись домена на IP **нового** сервера.

**SSL** на новом:
```bash
certbot --nginx -d my.cloudtelegram.ru
systemctl restart cloudtelegram
```

---

## 7. Обновление кода

```bash
cd /root/myproject/cloud
bash deploy/update.sh
# или: git pull && systemctl restart cloudtelegram
```

---

## 8. RU-VPS (Telegram заблокирован)

Нужен прокси — см. `deploy/PROXY.md` или WARP (`deploy/install-warp-docker.sh`).

Лучше сразу EU-VPS (как fra-1-vm-l0lo) — проще и стабильнее.

---

## Структура на сервере

```
/root/myproject/cloud/
├── .env              # секреты
├── .venv/            # Python
├── bot.py            # бот + веб
├── data/users/       # файлы пользователей
└── deploy/           # скрипты
```

Systemd: `cloudtelegram.service`  
Nginx: `/etc/nginx/conf.d/cloudtelegram.conf`
