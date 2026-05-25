#!/bin/bash
set -e

# Запуск: cd ~/myproject/cloud && bash deploy/install.sh

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
DOMAIN="my.cloudtelegram.ru"
PORT="6090"
VENV_DIR="${PROJECT_DIR}/.venv"

echo "==> Проект: $PROJECT_DIR"

if [ "$EUID" -ne 0 ]; then
  echo "Запустите от root: sudo bash deploy/install.sh"
  exit 1
fi

echo "==> Пакеты: nginx, certbot, python..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y nginx certbot python3-certbot-nginx python3-venv python3-full

echo "==> Виртуальное окружение Python..."
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r requirements.txt

echo "==> .env..."
if [ ! -f .env ]; then
  cp deploy/.env.example .env
  echo "Создан .env — вставьте BOT_TOKEN: nano .env"
else
  echo ".env уже есть"
fi

echo "==> Nginx (HTTP, certbot добавит HTTPS)..."
cat > /etc/nginx/conf.d/cloudtelegram.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }
}
EOF

nginx -t
systemctl enable nginx
systemctl restart nginx

echo "==> SSL-сертификат..."
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "admin@${DOMAIN}" || {
  echo "Certbot не выполнился. Позже вручную:"
  echo "  certbot --nginx -d ${DOMAIN}"
}

echo "==> Systemd..."
sed -e "s|/root/myproject/cloud|${PROJECT_DIR}|g" \
    -e "s|/root/myproject/cloud/.venv/bin/python|${VENV_DIR}/bin/python|g" \
    deploy/cloudtelegram.service > /etc/systemd/system/cloudtelegram.service
systemctl daemon-reload
systemctl enable cloudtelegram

echo ""
echo "============================================"
echo " 1. nano ${PROJECT_DIR}/.env  → BOT_TOKEN"
echo " 2. systemctl start cloudtelegram"
echo " 3. journalctl -u cloudtelegram -f"
echo " Веб: https://${DOMAIN}"
echo " Python: ${VENV_DIR}/bin/python"
echo "============================================"
