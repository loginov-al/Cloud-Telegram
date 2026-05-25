#!/bin/bash
# Обновление с GitHub одной командой
set -e

cd "$(dirname "$0")/.."

if [ ! -d .git ]; then
  echo "Это не git-репозиторий. Клонируйте заново:"
  echo "  git clone https://github.com/loginov-al/Cloud-Telegram.git ~/myproject/cloud"
  exit 1
fi

cp .env /tmp/env_backup 2>/dev/null || true
git pull
cp /tmp/env_backup .env 2>/dev/null || true

.venv/bin/pip install -r requirements.txt
systemctl restart cloudtelegram
sleep 2
systemctl status cloudtelegram --no-pager
