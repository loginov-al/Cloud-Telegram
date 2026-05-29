#!/bin/bash
# WARP через Docker → SOCKS5 на 127.0.0.1:1080 (только для Telegram-бота)
# Сначала MicroWARP (легче), затем zhengxiongzhao/warp-svc. Запуск: bash deploy/install-warp-docker.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Запустите от root: bash deploy/install-warp-docker.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
PROXY_PORT=1080
PROXY_URL="socks5h://127.0.0.1:${PROXY_PORT}"

test_proxy() {
  curl -s --max-time 10 -x "$PROXY_URL" \
    https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null | grep -q 'warp=on'
}

test_telegram() {
  curl -s --max-time 15 -x "$PROXY_URL" \
    -o /dev/null -w "%{http_code}" https://api.telegram.org 2>/dev/null | grep -qE "200|302|404"
}

echo "==> Остановка нативного warp-svc..."
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

docker rm -f cloudflare-warp microwarp 2>/dev/null || true

try_microwarp() {
  local endpoint="$1"
  echo "==> MicroWARP (endpoint: $endpoint)..."
  docker rm -f microwarp 2>/dev/null || true
  docker run -d \
    --name microwarp \
    --restart unless-stopped \
    --cap-add NET_ADMIN \
    --cap-add SYS_MODULE \
    --sysctl net.ipv4.conf.all.src_valid_mark=1 \
    -e "ENDPOINT_IP=${endpoint}" \
    -p "127.0.0.1:${PROXY_PORT}:1080" \
    -v microwarp-data:/etc/wireguard \
    ghcr.io/ccbkkb/microwarp:latest

  for i in $(seq 1 20); do
    if test_proxy; then
      echo "OK — MicroWARP работает ($endpoint)"
      return 0
    fi
    sleep 3
  done
  echo "FAIL — MicroWARP ($endpoint)"
  docker logs microwarp --tail 20 2>&1 || true
  return 1
}

try_warp_svc() {
  echo "==> zhengxiongzhao/warp-svc..."
  docker rm -f cloudflare-warp 2>/dev/null || true
  docker run -d \
    --name cloudflare-warp \
    --restart unless-stopped \
    --device /dev/net/tun \
    --cap-add NET_ADMIN \
    --cap-add MKNOD \
    --cap-add AUDIT_WRITE \
    --sysctl net.ipv4.ip_forward=1 \
    -p "127.0.0.1:${PROXY_PORT}:1080" \
    zhengxiongzhao/warp-svc:latest

  for i in $(seq 1 20); do
    if test_proxy; then
      echo "OK — warp-svc Docker работает"
      return 0
    fi
    sleep 3
  done
  echo "FAIL — warp-svc Docker"
  docker logs cloudflare-warp --tail 20 2>&1 || true
  return 1
}

if try_microwarp "162.159.192.1:4500"; then
  :
elif try_microwarp "162.159.193.10:2408"; then
  :
elif try_warp_svc; then
  :
else
  echo ""
  echo "FAIL — WARP на этом VPS не работает (часто блокируется провайдером)."
  echo "Надёжное решение — зарубежный SOCKS5: deploy/PROXY.md"
  echo "  1) Арендуйте VPS в EU/US"
  echo "  2) bash deploy/setup-proxy-server.sh  (на прокси-VPS)"
  echo "  3) TELEGRAM_PROXY=socks5h://user:pass@IP:1080 в .env"
  exit 1
fi

echo "==> Проверка Telegram API..."
if test_telegram; then
  echo "OK — api.telegram.org доступен через прокси"
else
  echo "WARN — Telegram через прокси не ответил (проверьте логи контейнера)"
fi

echo "==> Обновление .env..."
PROXY_LINE="TELEGRAM_PROXY=${PROXY_URL}"
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
echo "Готово. ${PROXY_LINE}"
echo "Проверка: curl -x ${PROXY_URL} https://www.cloudflare.com/cdn-cgi/trace | grep warp"
echo "Логи бота: journalctl -u cloudtelegram -f"
