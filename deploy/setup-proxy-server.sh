#!/bin/bash
# Запуск на ЗАРУБЕЖНОМ VPS (EU/US/Finland и т.д.) — НЕ на nsk-1-vm!
# apt install -y microsocks
# bash setup-proxy-server.sh

set -e

PROXY_USER="${PROXY_USER:-cloudbot}"
PROXY_PASS="${PROXY_PASS:-$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)}"
PROXY_PORT="${PROXY_PORT:-1080}"

echo "=== SOCKS5 прокси для Telegram ==="
echo ""
echo "1. Установка microsocks..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y microsocks openssl

echo "2. Systemd-сервис..."
cat > /etc/systemd/system/microsocks.service <<EOF
[Unit]
Description=SOCKS5 proxy for CloudTelegram
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/microsocks -i 0.0.0.0 -p ${PROXY_PORT} -u ${PROXY_USER} -P ${PROXY_PASS}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable microsocks
systemctl restart microsocks

SERVER_IP=$(curl -4 -s ifconfig.me || curl -4 -s icanhazip.com)

echo ""
echo "============================================"
echo "  Прокси готов!"
echo "============================================"
echo ""
echo "Добавьте в .env на ОСНОВНОМ сервере (nsk-1-vm):"
echo ""
echo "TELEGRAM_PROXY=socks5://${PROXY_USER}:${PROXY_PASS}@${SERVER_IP}:${PROXY_PORT}"
echo "TELEGRAM_TIMEOUT=120"
echo ""
echo "Затем: systemctl restart cloudtelegram"
echo ""
echo "⚠️  Откройте порт ${PROXY_PORT} в файрволе этого VPS!"
echo "============================================"
