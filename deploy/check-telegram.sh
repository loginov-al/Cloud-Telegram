#!/bin/bash
echo "=== Проверка доступа к Telegram API ==="
echo ""

echo -n "1. DNS api.telegram.org: "
getent hosts api.telegram.org || echo "FAIL"

echo -n "2. HTTPS (10 сек): "
if curl -s --max-time 10 -o /dev/null -w "%{http_code}" https://api.telegram.org | grep -q "200\|302\|404"; then
  echo "OK"
else
  echo "FAIL — заблокирован или недоступен"
fi

echo ""
echo "3. TELEGRAM_PROXY в .env:"
if [ -f .env ] && grep -q "^TELEGRAM_PROXY=" .env; then
  grep "^TELEGRAM_PROXY=" .env | sed 's/=.*/=***/'
else
  echo "   НЕ ЗАДАН — нужен SOCKS5-прокси за рубежом"
fi

echo ""
echo "=== Решение ==="
echo "Арендуйте VPS в EU/US, установите SOCKS5:"
echo "  apt install microsocks -y"
echo "  microsocks -i 0.0.0.0 -p 1080 -u user -P password"
echo ""
echo "В .env на этом сервере:"
echo "  TELEGRAM_PROXY=socks5://user:password@IP_ПРОКСИ:1080"
echo ""
echo "Затем: systemctl restart cloudtelegram"
