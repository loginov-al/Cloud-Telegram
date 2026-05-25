#!/bin/bash
# WARP через Docker → SOCKS5 на 127.0.0.1:1080 (только для Telegram-бота)
# Надёжнее нативного warp-svc на VPS. Запуск: bash deploy/install-warp-docker.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Запустите от root: bash deploy/install-warp-docker.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
PROXY_PORT=1080
CONTAINER_NAME=cloudflare-warp

echo "==> Остановка нативного warp-svc (конфликтует с Docker)..."
systemctl stop warp-svc 2>/dev/null || true
systemctl disable warp-svc 2>/dev/null || true

echo "==> Установка Docker (если нет)..."
if ! command -v docker >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y ca-certificates curl
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker 2>/dev/null || true

echo "==> Запуск WARP-контейнера..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --device /dev/net/tun \
  --cap-add NET_ADMIN \
  --cap-add MKNOD \
  --cap-add AUDIT_WRITE \
  --sysctl net.ipv4.ip_forward=1 \
  -p "127.0.0.1:${PROXY_PORT}:1080" \
  zhengxiongzhao/warp-svc:latest

echo "==> Ожидание регистрации WARP (до 60 сек)..."
for i in $(seq 1 30); do
  if curl -s --max-time 5 -x "socks5h://127.0.0.1:${PROXY_PORT}" \
      https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null | grep -q 'warp=on'; then
    echo "OK — WARP через Docker работает"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "FAIL — прокси не ответил за 60 сек"
    echo "Логи: docker logs $CONTAINER_NAME --tail 50"
    exit 1
  fi
  sleep 2
done

echo "==> Проверка Telegram API через прокси..."
if curl -s --max-time 15 -x "socks5h://127.0.0.1:${PROXY_PORT}" \
    -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302|404"; then
  echo "OK — api.telegram.org доступен"
else
  echo "FAIL — Telegram API недоступен даже через WARP"
  echo "Нужен зарубежный SOCKS5: deploy/PROXY.md"
  exit 1
fi

echo "==> Обновление .env..."
PROXY_LINE="TELEGRAM_PROXY=socks5://127.0.0.1:${PROXY_PORT}"
if [ -f "$ENV_FILE" ]; then
  if grep -q "^TELEGRAM_PROXY=" "$ENV_FILE"; then
    sed -i "s|^TELEGRAM_PROXY=.*|${PROXY_LINE}|" "$ENV_FILE"
  else
    echo "$PROXY_LINE" >> "$ENV_FILE"
  fi
else
  echo "$PROXY_LINE" > "$ENV_FILE"
fi

systemctl restart cloudtelegram 2>/dev/null || true

echo ""
echo "Готово. TELEGRAM_PROXY=socks5://127.0.0.1:${PROXY_PORT}"
echo "Проверка бота: journalctl -u cloudtelegram -f"
