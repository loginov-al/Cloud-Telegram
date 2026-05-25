# Свой SOCKS5-прокси для Telegram (5 минут)

Telegram API заблокирован на RU-VPS. Нужен **зарубежный** сервер.

## Шаг 1 — VPS за рубежом

Арендуйте самый дешёвый VPS в **EU / US / Finland** (~200–400 ₽/мес):
- Hetzner, DigitalOcean, Vultr, Timeweb Cloud (EU), и т.д.

## Шаг 2 — На прокси-VPS

```bash
ssh root@IP_ПРОКСИ_VPS
apt update && apt install -y git microsocks
```

Скопируйте скрипт или выполните вручную:

```bash
PROXY_USER=cloudbot
PROXY_PASS=MyStr0ngPass123
PROXY_PORT=1080

cat > /etc/systemd/system/microsocks.service <<EOF
[Unit]
Description=SOCKS5 proxy
After=network.target
[Service]
ExecStart=/usr/bin/microsocks -i 0.0.0.0 -p ${PROXY_PORT} -u ${PROXY_USER} -P ${PROXY_PASS}
Restart=always
[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now microsocks
curl -4 ifconfig.me   # запомните IP
```

**Откройте порт 1080** в файрволе прокси-VPS.

## Шаг 3 — На основном сервере (nsk-1-vm)

```bash
nano ~/myproject/cloud/.env
```

```
TELEGRAM_PROXY=socks5://cloudbot:MyStr0ngPass123@IP_ПРОКСИ:1080
TELEGRAM_TIMEOUT=120
```

```bash
systemctl restart cloudtelegram
journalctl -u cloudtelegram -f
```

Ожидайте: `Telegram подключён: @RUcloud1_bot`

## Проверка прокси с основного сервера

```bash
curl -x socks5://cloudbot:PASS@IP_ПРОКСИ:1080 --max-time 10 https://api.telegram.org
```

Должен ответить (не timeout).

## ⚠️ Бесплатные прокси из интернета

Не рекомендуется — нестабильны, могут перехватывать трафик (в т.ч. BOT_TOKEN).
