"""Текст документации для портала и вкладки «Справка»."""

import config


def _bot_link() -> str:
    return f"https://t.me/{config.BOT_USERNAME}"


def docs_html(compact: bool = False) -> str:
    """HTML блок документации. compact=True — для вкладки в панели."""
    bot = _bot_link()
    site = config.WEB_BASE_URL
    docs_site = config.DOCS_BASE_URL
    intro = "" if compact else f"""
    <div class="hero">
      <div class="logo">☁️</div>
      <h1>Облачный</h1>
      <p class="muted">Личное облачное хранилище в Telegram + веб-панель</p>
      <p><a class="btn btn-primary" href="{bot}">Открыть бота в Telegram</a></p>
    </div>"""

    return f"""{intro}
    <div class="card doc-section">
      <h2>🚀 Быстрый старт</h2>
      <ol class="steps">
        <li>Откройте <a href="{bot}">@{config.BOT_USERNAME}</a> в Telegram</li>
        <li>Нажмите <b>/start</b></li>
        <li>Отправьте боту любой файл — он сохранится в облако</li>
        <li>Управляйте файлами через меню или <b>🛠️ Файловый менеджер</b></li>
      </ol>
    </div>

    <div class="card doc-section">
      <h2>🌐 Веб-панель</h2>
      <p>Управление файлами из браузера — удобно на телефоне и ПК.</p>
      <ol class="steps">
        <li>В боте: <b>⚙️ Настройки → 🌐 Веб-панель</b></li>
        <li>Перейдите по персональной ссылке — она постоянная, сохраните в закладки</li>
        <li>Поиск, фильтры, скачивание, ZIP, публичные ссылки</li>
      </ol>
      <p class="muted">Панель: <a href="{site}">{site}</a> · Документация: <a href="{docs_site}">{docs_site}</a></p>
    </div>

    <div class="card doc-section">
      <h2>📁 Возможности бота</h2>
      <ul class="steps">
        <li><b>Загрузка</b> — документы, фото, видео, архивы</li>
        <li><b>Версии файлов</b> — при повторной загрузке с тем же именем</li>
        <li><b>Публичные ссылки</b> — с паролем и сроком действия</li>
        <li><b>ZIP-архив</b> — скачать все файлы одним архивом</li>
        <li><b>QR-код</b> — для публичных ссылок</li>
        <li><b>Inline-режим</b> — <code>@{config.BOT_USERNAME} имя_файла</code> в любом чате</li>
        <li><b>Лимит</b> — 5 GB на пользователя</li>
      </ul>
    </div>

    <div class="card doc-section">
      <h2>🔗 Публичные ссылки</h2>
      <ol class="steps">
        <li>🛠️ Файловый менеджер → выберите файл → 🔗 Создать ссылку</li>
        <li>Укажите срок (1 день — бессрочно) и пароль (опционально)</li>
        <li>Отправьте ссылку — получатель скачает файл через бота</li>
      </ol>
    </div>

    <div class="card doc-section">
      <h2>❓ Частые вопросы</h2>
      <p><b>Бот не отвечает?</b><br>Подождите 1–2 минуты после перезапуска сервера.</p>
      <p><b>Ссылка веб-панели не работает?</b><br>Получите ссылку заново: ⚙️ Настройки → 🌐 Веб-панель.</p>
      <p><b>Файл не загружается?</b><br>Проверьте лимит 5 GB в 💾 Использование хранилища.</p>
    </div>
    """
