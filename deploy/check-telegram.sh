#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "=== Проверка доступа к Telegram API ==="
echo ""

PROXY=""
if [ -f .env ]; then
  PROXY=$(grep "^TELEGRAM_PROXY=" .env | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

echo -n "1. DNS api.telegram.org: "
getent hosts api.telegram.org || echo "FAIL"

echo -n "2. HTTPS напрямую (10 сек): "
if curl -s --max-time 10 -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302|404"; then
  echo "OK"
else
  echo "FAIL — заблокирован или недоступен"
fi

echo ""
echo "3. TELEGRAM_PROXY в .env:"
if [ -n "$PROXY" ]; then
  echo "   ${PROXY/@*/@***}"
else
  echo "   НЕ ЗАДАН"
fi

if [ -n "$PROXY" ]; then
  echo ""
  echo -n "4. HTTPS через прокси (15 сек): "
  if curl -s --max-time 15 -x "$PROXY" -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -qE "200|302|404"; then
    echo "OK"
  else
    echo "FAIL — прокси не работает"
    echo "   docker ps -a"
    echo "   docker logs microwarp --tail 30 2>/dev/null || docker logs cloudflare-warp --tail 30"
  fi
fi

echo ""
echo "5. Docker WARP:"
docker ps -a --filter name=microwarp --filter name=cloudflare-warp --format '   {{.Names}}: {{.Status}}' 2>/dev/null || echo "   docker не установлен"

echo ""
echo "=== Решение ==="
echo "WARP не работает на RU-VPS → зарубежный SOCKS5 (deploy/PROXY.md):"
echo "  TELEGRAM_PROXY=socks5h://user:password@IP_ПРОКСИ:1080"
echo "  systemctl restart cloudtelegram"
