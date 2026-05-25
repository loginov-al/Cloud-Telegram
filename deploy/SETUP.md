# Установка на сервере (Ubuntu/Debian)

```bash
cd ~/myproject/cloud
bash deploy/install.sh
nano .env                    # BOT_TOKEN
systemctl start cloudtelegram
```

## Зависимости Python (venv)

Debian не даёт ставить pip в систему. Скрипт создаёт `.venv/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python bot.py
```

## После установки

```bash
systemctl status cloudtelegram
journalctl -u cloudtelegram -f
```

## Только venv вручную (если install.sh уже частично прошёл)

```bash
apt install -y python3-venv python3-full
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python bot.py
```
