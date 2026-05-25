#!/bin/bash
# Cloudflare WARP — обход блокировки Telegram на одном сервере
# Запуск: bash deploy/install-warp.sh

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Запустите от root: bash deploy/install-warp.sh"
  exit 1
fi

echo "==> Удаление неверного репозитория (если был)..."
rm -f /etc/apt/sources.list.d/cloudflare-client.list

echo "==> Установка Cloudflare WARP..."
export DEBIAN_FRONTEND=noninteractive
apt-get install -y curl gpg lsb-release

curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
  | gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg

# ВАЖНО: bookworm — не "cloudflare"!
echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" \
  > /etc/apt/sources.list.d/cloudflare-client.list

apt-get update -qq
apt-get install -y cloudflare-warp

echo "==> Запуск демона WARP..."
systemctl enable warp-svc
systemctl restart warp-svc

# Демону нужно время на старт сокета; без этого — "No such file or directory"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if warp-cli --accept-tos status >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Регистрация и подключение..."
# --accept-tos обязателен на headless-сервере (echo Y ломается с UTF-8 panic)
warp-cli --accept-tos registration delete 2>/dev/null || true
warp-cli --accept-tos registration new
warp-cli --accept-tos mode warp
warp-cli --accept-tos connect
sleep 5

echo "==> Статус WARP:"
if ! warp-cli --accept-tos status | grep -qi connected; then
  echo ""
  echo "FAIL — нативный WARP не подключился."
  echo "  Диагностика:  bash deploy/warp-diagnose.sh"
  echo "  Альтернатива: bash deploy/install-warp-docker.sh"
  echo "  Или SOCKS5:   deploy/PROXY.md"
  exit 1
fi

echo ""
echo "==> Проверка Telegram API..."
if curl -s --max-time 15 -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302|404"; then
  echo "OK — api.telegram.org доступен (системный WARP)"
else
  echo "WARN — Telegram напрямую недоступен; используйте Docker или SOCKS5:"
  echo "  bash deploy/install-warp-docker.sh"
  echo "  deploy/PROXY.md"
fi

systemctl restart cloudtelegram 2>/dev/null || true

echo ""
echo "Проверка бота: journalctl -u cloudtelegram -f"
