#!/bin/bash
# Диагностика WARP. Запуск: bash deploy/warp-diagnose.sh

echo "=== OS ==="
cat /etc/os-release 2>/dev/null | head -5

echo ""
echo "=== /dev/net/tun ==="
if [ -c /dev/net/tun ]; then
  echo "OK — TUN device exists"
else
  echo "MISSING — WARP не заработает без TUN (нужен модуль tun)"
  echo "  modprobe tun 2>/dev/null || echo 'modprobe tun failed'"
fi

echo ""
echo "=== cloudflare-warp package ==="
dpkg -l cloudflare-warp 2>/dev/null || echo "not installed"

echo ""
echo "=== warp-svc service ==="
systemctl is-active warp-svc 2>/dev/null || echo "inactive"
systemctl status warp-svc --no-pager -l 2>/dev/null | tail -15

echo ""
echo "=== warp-svc logs (last 20) ==="
journalctl -u warp-svc -n 20 --no-pager 2>/dev/null || echo "no logs"

echo ""
echo "=== IPC socket ==="
ls -la /run/cloudflare-warp/ 2>/dev/null || echo "/run/cloudflare-warp/ missing"

echo ""
echo "=== warp-cli status ==="
warp-cli --accept-tos status 2>&1 || true

echo ""
echo "=== curl direct (no proxy) ==="
curl -s --max-time 5 https://www.cloudflare.com/cdn-cgi/trace | grep -E 'warp|ip=' || echo "timeout/fail"
curl -s --max-time 5 -o /dev/null -w "telegram.org HTTP %{http_code}\n" https://api.telegram.org || echo "telegram timeout"

echo ""
echo "=== Docker WARP container ==="
docker ps -a --filter name=cloudflare-warp --format '{{.Names}} {{.Status}}' 2>/dev/null || echo "docker not available"

if docker ps --filter name=cloudflare-warp --format '{{.Names}}' 2>/dev/null | grep -q cloudflare-warp; then
  echo "--- docker logs (last 15) ---"
  docker logs cloudflare-warp --tail 15 2>&1
  echo "--- curl via docker proxy ---"
  curl -s --max-time 10 -x socks5h://127.0.0.1:1080 https://www.cloudflare.com/cdn-cgi/trace | grep warp || echo "proxy fail"
fi
