#!/bin/bash
# Пустой Ubuntu VPS (Timeweb EU) — SOCKS5 для Telegram
# Запуск: bash setup-proxy-ubuntu.sh

set -e
export DEBIAN_FRONTEND=noninteractive

MAIN_IP="${MAIN_IP:-213.171.15.70}"
PROXY_USER="${PROXY_USER:-cloudbot}"
PROXY_PASS="${PROXY_PASS:-$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)}"
PROXY_PORT="${PROXY_PORT:-1080}"

apt-get update -qq
apt-get install -y git gcc make openssl curl ufw

if ! command -v microsocks >/dev/null 2>&1; then
  rm -rf /tmp/microsocks
  git clone --depth 1 https://github.com/rofl0r/microsocks.git /tmp/microsocks
  make -C /tmp/microsocks
  install -m 755 /tmp/microsocks/microsocks /usr/local/bin/microsocks
fi

MS=$(command -v microsocks)

cat > /etc/systemd/system/microsocks.service <<EOF
[Unit]
Description=SOCKS5 for CloudTelegram
After=network.target

[Service]
Type=simple
ExecStart=${MS} -i 0.0.0.0 -p ${PROXY_PORT} -u ${PROXY_USER} -P ${PROXY_PASS}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now microsocks

ufw allow OpenSSH
ufw allow from "${MAIN_IP}" to any port "${PROXY_PORT}"
ufw --force enable

SERVER_IP=$(curl -4 -s ifconfig.me || curl -4 -s icanhazip.com)

echo ""
echo "============================================"
echo "  Прокси готов: ${SERVER_IP}:${PROXY_PORT}"
echo "  USER: ${PROXY_USER}"
echo "  PASS: ${PROXY_PASS}"
echo "============================================"
echo ""
echo "На nsk-1-vm выполните:"
echo ""
echo "cd ~/myproject/cloud && sed -i '/^TELEGRAM_PROXY=/d' .env && echo 'TELEGRAM_PROXY=socks5h://${PROXY_USER}:${PROXY_PASS}@${SERVER_IP}:${PROXY_PORT}' >> .env && grep -q '^TELEGRAM_TIMEOUT=' .env || echo 'TELEGRAM_TIMEOUT=120' >> .env && systemctl restart cloudtelegram && sleep 3 && journalctl -u cloudtelegram -n 10 --no-pager"
echo ""
echo "Timeweb: откройте TCP ${PROXY_PORT} для ${MAIN_IP} в панели firewall"
echo "============================================"
