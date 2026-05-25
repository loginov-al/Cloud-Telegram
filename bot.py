import asyncio
import fcntl
import hashlib
import logging
import os
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

import config
import storage
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    from aiogram.client.session.aiohttp import AiohttpSession

    if config.TELEGRAM_PROXY:
        from aiohttp_socks import ProxyConnector

        connector = ProxyConnector.from_url(config.TELEGRAM_PROXY)
        session = AiohttpSession(connector=connector, timeout=config.TELEGRAM_TIMEOUT)
        safe_proxy = config.TELEGRAM_PROXY.split("@")[-1]
        logger.info("Telegram через прокси: %s", safe_proxy)
    else:
        session = AiohttpSession(timeout=config.TELEGRAM_TIMEOUT)
        logger.warning(
            "TELEGRAM_PROXY не задан — на RU-VPS Telegram API часто заблокирован"
        )

    return Bot(token=config.token, session=session)


bot = create_bot()
db = Dispatcher(storage=MemoryStorage())
LOCK_FILE = Path(__file__).parent / ".bot.lock"

def get_main_keboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    # Кнопки Клавиатуры Telegram #

    builder.add(KeyboardButton(text="🗄️ Мои файлы"))
    builder.add(KeyboardButton(text="⚙️ Настройки"))
    builder.add(KeyboardButton(text="🛠️ Файловый менеджер"))
    
    # Распределяем кнопки: первые две в один ряд, третью — ниже
    builder.adjust(2, 1) 
    
    # Возвращаем клавиатуру с автоматическим изменением размера под экран телефона
    return builder.as_markup(resize_keyboard=True)


@db.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) > 1 and args[1].startswith("share_"):
        await _handle_share_link(message, args[1][6:], state)
        return

    used = _get_used_storage(message.from_user.id)
    free = max(STORAGE_LIMIT - used, 0)
    files_count = len(_get_user_files(message.from_user.id))
    percent = used * 100 // STORAGE_LIMIT if STORAGE_LIMIT else 0
    name = message.from_user.first_name or message.from_user.full_name
    me = await bot.get_me()
    bot_username = me.username or "бот"

    await message.answer(
        text=(
            f"👋 Привет, <b>{name}</b>!\n"
            f"Добро пожаловать в <b>Облачный</b> — твоё личное хранилище файлов в Telegram.\n\n"
            f"💾 <b>Хранилище</b>\n"
            f"{_storage_bar(used, STORAGE_LIMIT)} {percent}%\n"
            f"Свободно: <b>{_format_size(free)}</b> · Занято: <b>{_format_size(used)}</b> · Лимит: <b>{_format_size(STORAGE_LIMIT)}</b>\n"
            f"📁 Файлов: <b>{files_count}</b>\n\n"
            f"🚀 Быстрая загрузка и скачивание\n"
            f"🔗 Публичные ссылки с паролем и сроком\n"
            f"📱 Inline: @{bot_username} имя_файла\n"
            f"🔒 Безопасное хранение на сервере\n\n"
            f"Выберите раздел на клавиатуре ниже 👇"
        ),
        reply_markup=get_main_keboard(),
        parse_mode="HTML",
    )



# --- Мои файлы: хранилище и клавиатуры ---

STORAGE_LIMIT = storage.STORAGE_LIMIT
DATA_DIR = storage.DATA_DIR
USER_FILES = storage.USER_FILES
PUBLIC_LINKS = storage.PUBLIC_LINKS
USER_SETTINGS = storage.USER_SETTINGS
LINK_DRAFTS = storage.LINK_DRAFTS

DEFAULT_SETTINGS = storage.DEFAULT_SETTINGS

DURATION_OPTIONS = {
    "1h": ("1 час", timedelta(hours=1)),
    "1d": ("1 день", timedelta(days=1)),
    "7d": ("7 дней", timedelta(days=7)),
    "30d": ("30 дней", timedelta(days=30)),
    "forever": ("Бессрочно", None),
}


class CreateLinkStates(StatesGroup):
    choosing_file = State()
    choosing_duration = State()
    entering_password = State()


class FileManagerStates(StatesGroup):
    waiting_upload = State()
    waiting_rename = State()
    waiting_new_version = State()


class SettingsStates(StatesGroup):
    confirming_clear = State()


class ShareLinkStates(StatesGroup):
    entering_password = State()


def get_my_files_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📂 Список файлов"))
    builder.add(KeyboardButton(text="🔗 Создать публичную ссылку"))
    builder.add(KeyboardButton(text="📋 Активные ссылки"))
    builder.add(KeyboardButton(text="📦 Скачать всё ZIP"))
    builder.add(KeyboardButton(text="◀️ Главное меню"))
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 ** 2:.1f} MB"


def _get_user_files(user_id: int) -> list[dict]:
    return storage.get_user_files(user_id)


def _get_user_settings(user_id: int) -> dict:
    return storage.get_user_settings(user_id)


def _get_user_dir(user_id: int) -> Path:
    return storage._get_user_dir(user_id)


def _get_used_storage(user_id: int) -> int:
    return storage.get_used_storage(user_id)


def _find_file(user_id: int, file_id: str) -> dict | None:
    return storage.find_file(user_id, file_id)


def _unique_filename(user_id: int, name: str) -> str:
    return storage.unique_filename(user_id, name)


def _remove_public_links_for_file(user_id: int, file_id: str) -> None:
    storage.remove_public_links_for_file(user_id, file_id)


def _storage_bar(used: int, limit: int, width: int = 10) -> str:
    ratio = min(used / limit, 1.0) if limit else 0
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def _extract_upload_info(message: Message) -> tuple[str, str, int, str] | None:
    if message.document:
        doc = message.document
        return doc.file_id, doc.file_name or "document", doc.file_size or 0, "document"
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, f"photo_{photo.file_unique_id}.jpg", photo.file_size or 0, "photo"
    if message.video:
        vid = message.video
        return vid.file_id, vid.file_name or f"video_{vid.file_unique_id}.mp4", vid.file_size or 0, "video"
    if message.audio:
        aud = message.audio
        return aud.file_id, aud.file_name or f"audio_{aud.file_unique_id}.mp3", aud.file_size or 0, "audio"
    if message.voice:
        voice = message.voice
        return voice.file_id, f"voice_{voice.file_unique_id}.ogg", voice.file_size or 0, "voice"
    return None


def _build_files_inline_keyboard(user_id: int, prefix: str) -> InlineKeyboardMarkup | None:
    files = _get_user_files(user_id)
    if not files:
        return None
    builder = InlineKeyboardBuilder()
    for file in files:
        builder.row(
            InlineKeyboardButton(
                text=f"📄 {file['name']} ({_format_size(file['size'])})",
                callback_data=f"{prefix}:{file['id']}",
            )
        )
    return builder.as_markup()


def _build_duration_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (label, _) in DURATION_OPTIONS.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"link_dur:{key}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="link_cancel"))
    return builder.as_markup()


def _build_password_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔓 Без пароля", callback_data="link_nopass"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="link_cancel"))
    return builder.as_markup()


def _format_expires(expires_at: datetime | None) -> str:
    if expires_at is None:
        return "бессрочно"
    return expires_at.strftime("%d.%m.%Y %H:%M")


def _user_links(user_id: int) -> list[tuple[str, dict]]:
    return [
        (token, link)
        for token, link in PUBLIC_LINKS.items()
        if link["user_id"] == user_id
    ]


def _save_link_draft(user_id: int, **data) -> None:
    draft = LINK_DRAFTS.setdefault(user_id, {})
    draft.update(data)


def _get_link_draft(user_id: int) -> dict:
    return LINK_DRAFTS.get(user_id, {})


def _clear_link_draft(user_id: int) -> None:
    LINK_DRAFTS.pop(user_id, None)


async def _get_link_session(state: FSMContext, user_id: int) -> dict:
    data = await state.get_data()
    draft = _get_link_draft(user_id)
    return {**draft, **data}


async def _get_bot_link(token: str) -> str:
    me = await bot.get_me()
    return f"https://t.me/{me.username}?start=share_{token}"


async def _send_link_qr(message: Message, public_url: str) -> None:
    qr_buffer = storage.generate_qr_bytes(public_url)
    await message.answer_photo(
        BufferedInputFile(qr_buffer.read(), filename="link_qr.png"),
        caption="📱 QR-код для публичной ссылки — можно распечатать или показать офлайн.",
    )


@db.inline_query()
async def inline_file_search(inline_query: InlineQuery):
    query = inline_query.query.strip().lower()
    files = _get_user_files(inline_query.from_user.id)
    if query:
        files = [file for file in files if query in file["name"].lower()]

    results = []
    for index, file in enumerate(files[:50]):
        tg_file_id = file.get("telegram_file_id")
        if not tg_file_id:
            continue
        description = f"{_format_size(file['size'])} · v{file.get('current_version', 1)}"
        if file["type"] == "photo":
            results.append(
                InlineQueryResultCachedPhoto(
                    id=f"{file['id']}:{index}",
                    photo_file_id=tg_file_id,
                    title=file["name"],
                    description=description,
                )
            )
        else:
            results.append(
                InlineQueryResultCachedDocument(
                    id=f"{file['id']}:{index}",
                    document_file_id=tg_file_id,
                    title=file["name"],
                    description=description,
                )
            )

    if not results and inline_query.from_user.id:
        me = await bot.get_me()
        results.append(
            InlineQueryResultArticle(
                id="help",
                title="Облачный — файлы не найдены",
                description="Загрузите файлы через бота или измените запрос",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"Откройте @{me.username} → 🛠️ Файловый менеджер → ⬆️ Загрузить файл"
                    )
                ),
            )
        )

    await inline_query.answer(results, cache_time=5, is_personal=True)


# Обработчики Клавиатуры #

@db.message(F.text == "🗄️ Мои файлы")
async def my_files_handler(message: Message, state: FSMContext):
    await state.clear()
    files_count = len(_get_user_files(message.from_user.id))
    await message.answer(
        text=(
            "🗄️ <b>Мои файлы</b>\n\n"
            f"Файлов в облаке: <b>{files_count}</b>\n\n"
            "Выберите действие:"
        ),
        reply_markup=get_my_files_keyboard(),
        parse_mode="HTML",
    )


@db.message(F.text == "◀️ Главное меню")
async def back_to_main_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_keboard())


@db.message(F.text == "📂 Список файлов")
async def files_list_handler(message: Message):
    files = _get_user_files(message.from_user.id)
    if not files:
        await message.answer(
            "📂 У вас пока нет файлов.\n"
            "Загрузите их через 🛠️ Файловый менеджер.",
            reply_markup=get_my_files_keyboard(),
        )
        return

    lines = ["📂 <b>Ваши файлы:</b>\n"]
    for i, file in enumerate(files, 1):
        lines.append(
            f"{i}. <b>{file['name']}</b>\n"
            f"   Размер: {_format_size(file['size'])} · ID: <code>{file['id']}</code>"
        )
    await message.answer(
        "\n".join(lines),
        reply_markup=get_my_files_keyboard(),
        parse_mode="HTML",
    )


@db.message(F.text == "🔗 Создать публичную ссылку")
async def create_link_start_handler(message: Message, state: FSMContext):
    keyboard = _build_files_inline_keyboard(message.from_user.id, "link_file")
    if not keyboard:
        await message.answer(
            "Нет файлов для публикации.\nСначала загрузите файл через 🛠️ Файловый менеджер.",
            reply_markup=get_my_files_keyboard(),
        )
        return

    _clear_link_draft(message.from_user.id)
    await state.set_state(CreateLinkStates.choosing_file)
    await message.answer(
        "Выберите файл для публичной ссылки:",
        reply_markup=keyboard,
    )


@db.callback_query(F.data.startswith("link_file:"))
async def link_choose_file_handler(callback: CallbackQuery, state: FSMContext):
    file_id = callback.data.split(":", 1)[1]
    user_files = {f["id"]: f for f in _get_user_files(callback.from_user.id)}
    if file_id not in user_files:
        await callback.answer("Файл не найден", show_alert=True)
        return

    await state.update_data(file_id=file_id, file_name=user_files[file_id]["name"])
    _save_link_draft(
        callback.from_user.id,
        file_id=file_id,
        file_name=user_files[file_id]["name"],
    )
    await state.set_state(CreateLinkStates.choosing_duration)
    await callback.message.edit_text(
        f"📄 Файл: <b>{user_files[file_id]['name']}</b>\n\n"
        "Выберите срок доступа к ссылке:",
        reply_markup=_build_duration_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@db.callback_query(F.data.startswith("link_dur:"))
async def link_choose_duration_handler(callback: CallbackQuery, state: FSMContext):
    duration_key = callback.data.split(":", 1)[1]
    if duration_key not in DURATION_OPTIONS:
        await callback.answer("Неверный срок", show_alert=True)
        return

    label, delta = DURATION_OPTIONS[duration_key]
    expires_at = None if delta is None else datetime.now() + delta
    expires_raw = expires_at.isoformat() if expires_at else None
    await state.update_data(duration_key=duration_key, expires_at=expires_raw)
    _save_link_draft(
        callback.from_user.id,
        duration_key=duration_key,
        expires_at=expires_raw,
    )
    await state.set_state(CreateLinkStates.entering_password)
    await callback.message.edit_text(
        f"⏱ Срок доступа: <b>{label}</b>\n\n"
        "Введите пароль для ссылки или выберите доступ без пароля:",
        reply_markup=_build_password_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@db.callback_query(F.data == "link_nopass", StateFilter(CreateLinkStates.entering_password))
async def link_no_password_handler(callback: CallbackQuery, state: FSMContext):
    await _finalize_public_link(callback, state, password=None)


@db.message(StateFilter(CreateLinkStates.entering_password), F.text)
async def link_password_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        _clear_link_draft(message.from_user.id)
        await message.answer("❌ Создание ссылки отменено.", reply_markup=get_main_keboard())
        return

    password = message.text.strip()
    if len(password) < 4:
        await message.answer(
            "Пароль должен быть не короче 4 символов.\n"
            "Попробуйте снова или нажмите «🔓 Без пароля» в сообщении выше.",
        )
        return
    await _finalize_public_link(message, state, password=password)


async def _finalize_public_link(event: Message | CallbackQuery, state: FSMContext, password: str | None):
    user_id = event.from_user.id
    data = await _get_link_session(state, user_id)
    file_id = data.get("file_id")
    file_name = data.get("file_name", "файл")
    expires_raw = data.get("expires_at")

    if not file_id:
        text = "Сессия истекла. Начните создание ссылки заново."
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
            await event.answer("Сессия истекла", show_alert=True)
        else:
            await event.answer(text, reply_markup=get_my_files_keyboard())
        await state.clear()
        _clear_link_draft(user_id)
        return

    token = secrets.token_urlsafe(10)
    expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None

    PUBLIC_LINKS[token] = {
        "file_id": file_id,
        "file_name": file_name,
        "user_id": user_id,
        "expires_at": expires_at,
        "password_hash": _hash_password(password) if password else None,
        "downloads": 0,
        "created_at": datetime.now(),
    }

    try:
        public_url = await _get_bot_link(token)
    except Exception as exc:
        logger.exception("Не удалось получить ссылку бота")
        error_text = "❌ Не удалось создать ссылку. Попробуйте ещё раз."
        if isinstance(event, CallbackQuery):
            await event.message.answer(error_text, reply_markup=get_my_files_keyboard())
            await event.answer("Ошибка", show_alert=True)
        else:
            await event.answer(error_text, reply_markup=get_my_files_keyboard())
        await state.clear()
        _clear_link_draft(user_id)
        return

    password_line = f"🔑 Пароль: <code>{password}</code>\n" if password else "🔓 Доступ без пароля\n"

    result_text = (
        "✅ <b>Публичная ссылка создана!</b>\n\n"
        f"📄 Файл: <b>{file_name}</b>\n"
        f"⏱ Действует до: <b>{_format_expires(expires_at)}</b>\n"
        f"{password_line}\n"
        f"🔗 Ссылка:\n<code>{public_url}</code>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            "✅ Ссылка создана! Результат отправлен ниже.",
            parse_mode="HTML",
        )
        await event.message.answer(
            result_text,
            reply_markup=get_my_files_keyboard(),
            parse_mode="HTML",
        )
        await _send_link_qr(event.message, public_url)
        await event.answer("Ссылка создана!")
    else:
        await event.answer(result_text, reply_markup=get_my_files_keyboard(), parse_mode="HTML")
        await _send_link_qr(event, public_url)

    await state.clear()
    _clear_link_draft(user_id)
    storage.persist_user(user_id)


@db.callback_query(F.data == "link_cancel")
async def link_cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    _clear_link_draft(callback.from_user.id)
    await callback.message.edit_text("❌ Создание ссылки отменено.")
    await callback.answer()


@db.message(F.text == "📋 Активные ссылки")
async def active_links_handler(message: Message):
    links = _user_links(message.from_user.id)
    now = datetime.now()
    active = []
    expired_tokens = []

    for token, link in links:
        expires_at = link.get("expires_at")
        if expires_at and expires_at < now:
            expired_tokens.append(token)
            continue
        active.append((token, link))

    for token in expired_tokens:
        PUBLIC_LINKS.pop(token, None)

    if not active:
        await message.answer(
            "📋 У вас нет активных публичных ссылок.\n"
            "Создайте новую через «🔗 Создать публичную ссылку».",
            reply_markup=get_my_files_keyboard(),
        )
        return

    lines = ["📋 <b>Активные ссылки:</b>\n"]
    for i, (token, link) in enumerate(active, 1):
        expires_at = link.get("expires_at")
        has_password = "да" if link.get("password_hash") else "нет"
        public_url = await _get_bot_link(token)
        lines.append(
            f"{i}. <b>{link['file_name']}</b>\n"
            f"   ⏱ до {_format_expires(expires_at)} · 🔑 пароль: {has_password}\n"
            f"   📥 скачиваний: {link.get('downloads', 0)}\n"
            f"   🔗 <code>{public_url}</code>\n"
        )

    await message.answer(
        "\n".join(lines),
        reply_markup=get_my_files_keyboard(),
        parse_mode="HTML",
    )


@db.message(F.text == "📦 Скачать всё ZIP")
async def download_all_zip_handler(message: Message, state: FSMContext):
    await state.clear()
    files = _get_user_files(message.from_user.id)
    if not files:
        await message.answer("Нет файлов для архивации.", reply_markup=get_my_files_keyboard())
        return

    await message.answer("⏳ Собираю архив...")
    zip_path = storage.create_user_zip(message.from_user.id)
    if not zip_path:
        await message.answer("❌ Не удалось создать архив.", reply_markup=get_my_files_keyboard())
        return

    await message.answer_document(
        FSInputFile(zip_path, filename="cloud_files.zip"),
        caption=f"📦 Архив из {len(files)} файлов",
        reply_markup=get_my_files_keyboard(),
    )


# --- Файловый менеджер ---

def get_file_manager_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="⬆️ Загрузить файл"))
    builder.add(KeyboardButton(text="📥 Скачать файл"))
    builder.add(KeyboardButton(text="🔄 Новая версия"))
    builder.add(KeyboardButton(text="✏️ Переименовать"))
    builder.add(KeyboardButton(text="🗑️ Удалить файл"))
    builder.add(KeyboardButton(text="📦 Скачать всё ZIP"))
    builder.add(KeyboardButton(text="◀️ Главное меню"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def _build_fm_action_keyboard(user_id: int, prefix: str) -> InlineKeyboardMarkup | None:
    files = _get_user_files(user_id)
    if not files:
        return None
    builder = InlineKeyboardBuilder()
    for file in files:
        builder.row(
            InlineKeyboardButton(
                text=f"📄 {file['name']} ({_format_size(file['size'])})",
                callback_data=f"{prefix}:{file['id']}",
            )
        )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="fm_cancel"))
    return builder.as_markup()


async def _save_uploaded_file(message: Message) -> dict | None:
    upload = _extract_upload_info(message)
    if not upload:
        return None

    tg_file_id, original_name, size, file_type = upload
    user_id = message.from_user.id
    used = _get_used_storage(user_id)

    if used + size > STORAGE_LIMIT:
        return None

    file_id = secrets.token_hex(6)
    safe_name = _unique_filename(user_id, original_name)
    user_dir = _get_user_dir(user_id)
    local_path = user_dir / f"{file_id}_{safe_name}"

    tg_file = await bot.get_file(tg_file_id)
    await bot.download_file(tg_file.file_path, local_path)

    record = {
        "id": file_id,
        "name": safe_name,
        "size": size,
        "path": str(local_path),
        "telegram_file_id": tg_file_id,
        "type": file_type,
        "uploaded_at": datetime.now(),
        "versions": [],
        "current_version": 1,
    }
    _get_user_files(user_id).append(record)
    storage.persist_user(user_id)
    return record


@db.message(F.text == "🛠️ Файловый менеджер")
async def file_manager_handler(message: Message, state: FSMContext):
    await state.clear()
    files = _get_user_files(message.from_user.id)
    used = _get_used_storage(message.from_user.id)
    await message.answer(
        text=(
            "🛠️ <b>Файловый менеджер</b>\n\n"
            f"📁 Файлов: <b>{len(files)}</b>\n"
            f"💾 Занято: <b>{_format_size(used)}</b> / {_format_size(STORAGE_LIMIT)}\n"
            f"{_storage_bar(used, STORAGE_LIMIT)} {used * 100 // STORAGE_LIMIT}%\n\n"
            "Выберите действие:"
        ),
        reply_markup=get_file_manager_keyboard(),
        parse_mode="HTML",
    )


@db.message(F.text == "⬆️ Загрузить файл")
async def upload_start_handler(message: Message, state: FSMContext):
    used = _get_used_storage(message.from_user.id)
    if used >= STORAGE_LIMIT:
        await message.answer(
            "❌ Хранилище заполнено. Удалите файлы или увеличьте лимит в настройках.",
            reply_markup=get_file_manager_keyboard(),
        )
        return

    await state.set_state(FileManagerStates.waiting_upload)
    free = STORAGE_LIMIT - used
    await message.answer(
        f"Отправьте файл (документ, фото, видео, аудио или голосовое).\n"
        f"Свободно: <b>{_format_size(free)}</b>",
        reply_markup=get_file_manager_keyboard(),
        parse_mode="HTML",
    )


@db.message(
    FileManagerStates.waiting_upload,
    F.document | F.photo | F.video | F.audio | F.voice,
)
async def upload_file_handler(message: Message, state: FSMContext):
    upload = _extract_upload_info(message)
    if not upload:
        await message.answer("Неподдерживаемый тип файла.", reply_markup=get_file_manager_keyboard())
        return

    _, _, size, _ = upload
    used = _get_used_storage(message.from_user.id)
    if used + size > STORAGE_LIMIT:
        await state.clear()
        await message.answer(
            f"❌ Недостаточно места. Нужно {_format_size(size)}, свободно {_format_size(STORAGE_LIMIT - used)}.",
            reply_markup=get_file_manager_keyboard(),
        )
        return

    await message.answer("⏳ Загружаю файл в облако...")
    record = await _save_uploaded_file(message)
    await state.clear()

    if not record:
        await message.answer("❌ Не удалось сохранить файл.", reply_markup=get_file_manager_keyboard())
        return

    settings = _get_user_settings(message.from_user.id)
    notify = "🔔 Файл сохранён в облаке." if settings["notifications"] else ""
    await message.answer(
        f"✅ <b>Файл загружен!</b>\n\n"
        f"📄 {record['name']}\n"
        f"📦 {_format_size(record['size'])}\n"
        f"🆔 <code>{record['id']}</code>"
        + (f"\n\n{notify}" if notify else ""),
        reply_markup=get_file_manager_keyboard(),
        parse_mode="HTML",
    )


@db.message(FileManagerStates.waiting_upload)
async def upload_invalid_handler(message: Message):
    if message.text == "◀️ Главное меню":
        return
    await message.answer(
        "Отправьте файл или нажмите «◀️ Главное меню» для выхода.",
        reply_markup=get_file_manager_keyboard(),
    )


@db.message(F.text == "📥 Скачать файл")
async def download_start_handler(message: Message):
    keyboard = _build_fm_action_keyboard(message.from_user.id, "fm_dl")
    if not keyboard:
        await message.answer("Нет файлов для скачивания.", reply_markup=get_file_manager_keyboard())
        return
    await message.answer("Выберите файл для скачивания:", reply_markup=keyboard)


@db.callback_query(F.data.startswith("fm_dl:"))
async def download_file_handler(callback: CallbackQuery):
    file_id = callback.data.split(":", 1)[1]
    file = _find_file(callback.from_user.id, file_id)
    if not file:
        await callback.answer("Файл не найден", show_alert=True)
        return

    path = Path(file["path"])
    if not path.exists():
        await callback.answer("Файл отсутствует на сервере", show_alert=True)
        return

    await callback.message.edit_text(f"📤 Отправляю <b>{file['name']}</b>...", parse_mode="HTML")
    await callback.message.answer_document(FSInputFile(path, filename=file["name"]))
    await callback.answer("Файл отправлен!")


@db.message(F.text == "✏️ Переименовать")
async def rename_start_handler(message: Message, state: FSMContext):
    keyboard = _build_fm_action_keyboard(message.from_user.id, "fm_rn")
    if not keyboard:
        await message.answer("Нет файлов для переименования.", reply_markup=get_file_manager_keyboard())
        return
    await state.set_state(FileManagerStates.waiting_rename)
    await message.answer("Выберите файл для переименования:", reply_markup=keyboard)


@db.callback_query(F.data.startswith("fm_rn:"))
async def rename_choose_handler(callback: CallbackQuery, state: FSMContext):
    file_id = callback.data.split(":", 1)[1]
    file = _find_file(callback.from_user.id, file_id)
    if not file:
        await callback.answer("Файл не найден", show_alert=True)
        return

    await state.update_data(rename_file_id=file_id)
    await callback.message.edit_text(
        f"📄 Текущее имя: <b>{file['name']}</b>\n\n"
        "Введите новое имя файла:",
        parse_mode="HTML",
    )
    await callback.answer()


@db.message(FileManagerStates.waiting_rename, F.text)
async def rename_apply_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        return

    new_name = message.text.strip()
    if not new_name or len(new_name) > 128:
        await message.answer("Имя должно быть от 1 до 128 символов.", reply_markup=get_file_manager_keyboard())
        return

    data = await state.get_data()
    file_id = data.get("rename_file_id")
    file = _find_file(message.from_user.id, file_id) if file_id else None
    if not file:
        await state.clear()
        await message.answer("Файл не найден.", reply_markup=get_file_manager_keyboard())
        return

    old_path = Path(file["path"])
    new_path = old_path.parent / f"{file_id}_{new_name}"
    if new_path.exists() and new_path != old_path:
        await message.answer("Файл с таким именем уже существует.", reply_markup=get_file_manager_keyboard())
        return

    old_path.rename(new_path)
    file["name"] = new_name
    file["path"] = str(new_path)
    await state.clear()
    storage.persist_user(message.from_user.id)

    await message.answer(
        f"✅ Файл переименован в <b>{new_name}</b>",
        reply_markup=get_file_manager_keyboard(),
        parse_mode="HTML",
    )


@db.message(F.text == "🔄 Новая версия")
async def new_version_start_handler(message: Message, state: FSMContext):
    keyboard = _build_fm_action_keyboard(message.from_user.id, "fm_ver")
    if not keyboard:
        await message.answer("Нет файлов для обновления.", reply_markup=get_file_manager_keyboard())
        return
    await message.answer("Выберите файл для загрузки новой версии:", reply_markup=keyboard)


@db.callback_query(F.data.startswith("fm_ver:"))
async def new_version_choose_handler(callback: CallbackQuery, state: FSMContext):
    file_id = callback.data.split(":", 1)[1]
    file = _find_file(callback.from_user.id, file_id)
    if not file:
        await callback.answer("Файл не найден", show_alert=True)
        return

    await state.set_state(FileManagerStates.waiting_new_version)
    await state.update_data(version_file_id=file_id)
    version_num = file.get("current_version", 1)
    await callback.message.edit_text(
        f"📄 Файл: <b>{file['name']}</b> (версия {version_num})\n\n"
        "Отправьте новый файл — текущая версия сохранится в истории.",
        parse_mode="HTML",
    )
    await callback.answer()


@db.message(
    FileManagerStates.waiting_new_version,
    F.document | F.photo | F.video | F.audio | F.voice,
)
async def new_version_upload_handler(message: Message, state: FSMContext):
    upload = _extract_upload_info(message)
    if not upload:
        await message.answer("Неподдерживаемый тип файла.", reply_markup=get_file_manager_keyboard())
        return

    tg_file_id, _, size, _ = upload
    user_id = message.from_user.id
    data = await state.get_data()
    file_id = data.get("version_file_id")
    file = _find_file(user_id, file_id) if file_id else None
    if not file:
        await state.clear()
        await message.answer("Файл не найден.", reply_markup=get_file_manager_keyboard())
        return

    used = _get_used_storage(user_id)
    if used + size > STORAGE_LIMIT:
        await state.clear()
        await message.answer("❌ Недостаточно места для новой версии.", reply_markup=get_file_manager_keyboard())
        return

    await message.answer("⏳ Сохраняю новую версию...")
    user_dir = _get_user_dir(user_id)
    new_path = user_dir / f"{file_id}_{file['name']}"
    tg_file = await bot.get_file(tg_file_id)
    await bot.download_file(tg_file.file_path, new_path)

    updated = storage.add_file_version(user_id, file_id, new_path, size, tg_file_id)
    await state.clear()

    if not updated:
        await message.answer("❌ Не удалось обновить файл.", reply_markup=get_file_manager_keyboard())
        return

    await message.answer(
        f"✅ <b>Новая версия сохранена!</b>\n\n"
        f"📄 {updated['name']}\n"
        f"📦 {_format_size(updated['size'])}\n"
        f"🔢 Версия: <b>{updated['current_version']}</b>\n"
        f"🗂 В истории: <b>{len(updated.get('versions', []))}</b> версий",
        reply_markup=get_file_manager_keyboard(),
        parse_mode="HTML",
    )


@db.message(FileManagerStates.waiting_new_version)
async def new_version_invalid_handler(message: Message):
    if message.text in {"◀️ Главное меню", "📦 Скачать всё ZIP"}:
        return
    await message.answer(
        "Отправьте файл или вернитесь в главное меню.",
        reply_markup=get_file_manager_keyboard(),
    )


@db.message(F.text == "🗑️ Удалить файл")
async def delete_start_handler(message: Message):
    keyboard = _build_fm_action_keyboard(message.from_user.id, "fm_del")
    if not keyboard:
        await message.answer("Нет файлов для удаления.", reply_markup=get_file_manager_keyboard())
        return
    await message.answer("Выберите файл для удаления:", reply_markup=keyboard)


@db.callback_query(F.data.startswith("fm_del:"))
async def delete_confirm_handler(callback: CallbackQuery):
    file_id = callback.data.split(":", 1)[1]
    file = _find_file(callback.from_user.id, file_id)
    if not file:
        await callback.answer("Файл не найден", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"fm_del_yes:{file_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="fm_cancel"),
    )
    await callback.message.edit_text(
        f"🗑️ Удалить файл <b>{file['name']}</b> ({_format_size(file['size'])})?\n"
        "Публичные ссылки на этот файл тоже будут удалены.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@db.callback_query(F.data.startswith("fm_del_yes:"))
async def delete_file_handler(callback: CallbackQuery):
    file_id = callback.data.split(":", 1)[1]
    file = storage.delete_file_record(callback.from_user.id, file_id)
    if not file:
        await callback.answer("Файл не найден", show_alert=True)
        return

    await callback.message.edit_text(f"✅ Файл <b>{file['name']}</b> удалён.", parse_mode="HTML")
    await callback.answer("Удалено!")


@db.callback_query(F.data == "fm_cancel")
async def fm_cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()


# --- Настройки ---

def get_settings_keyboard(notifications: bool) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="👤 Мой профиль"))
    builder.add(KeyboardButton(text="💾 Использование хранилища"))
    builder.add(KeyboardButton(text="ℹ️ О проекте"))
    builder.add(KeyboardButton(text="🌐 Веб-панель"))
    notify_label = "🔕 Выкл. уведомления" if notifications else "🔔 Вкл. уведомления"
    builder.add(KeyboardButton(text=notify_label))
    builder.add(KeyboardButton(text="🗑️ Очистить все файлы"))
    builder.add(KeyboardButton(text="◀️ Главное меню"))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


@db.message(F.text == "⚙️ Настройки")
async def settings_handler(message: Message, state: FSMContext):
    await state.clear()
    settings = _get_user_settings(message.from_user.id)
    await message.answer(
        text=(
            "⚙️ <b>Настройки</b>\n\n"
            f"🔔 Уведомления: {'включены' if settings['notifications'] else 'выключены'}\n"
            f"🌐 Язык: русский\n\n"
            "Выберите раздел:"
        ),
        reply_markup=get_settings_keyboard(settings["notifications"]),
        parse_mode="HTML",
    )


@db.message(F.text == "ℹ️ О проекте")
async def about_project_handler(message: Message):
    me = await bot.get_me()
    bot_link = f"@{me.username}" if me.username else me.full_name

    await message.answer(
        text=(
            "ℹ️ <b>О проекте «Облачный»</b>\n\n"
            "Telegram-бот для хранения, управления и обмена файлами прямо в мессенджере.\n\n"
            "<b>Возможности:</b>\n"
            "🛠️ Файловый менеджер — загрузка, скачивание, переименование и удаление\n"
            "🗄️ Личное облако — все файлы в одном месте\n"
            "🔗 Публичные ссылки — с паролем и ограничением по сроку\n"
            "📱 Inline-режим — @бот имя_файла в любом чате\n"
            "📦 ZIP-архив всех файлов одной кнопкой\n"
            "🔄 Версии файлов с историей изменений\n"
            "🌐 Веб-панель для управления через браузер\n"
            "💾 До 5 ГБ бесплатного хранилища на пользователя\n"
            "🔒 Файлы хранятся на защищённом сервере\n\n"
            f"🤖 Бот: {bot_link}\n"
            "📦 Версия: <code>1.1</code>\n"
            "🌐 Язык интерфейса: русский"
        ),
        reply_markup=get_settings_keyboard(_get_user_settings(message.from_user.id)["notifications"]),
        parse_mode="HTML",
    )


@db.message(F.text == "🌐 Веб-панель")
async def web_panel_handler(message: Message):
    token = storage.create_web_session(message.from_user.id)
    url = f"{config.WEB_BASE_URL}/?token={token}"
    await message.answer(
        text=(
            "🌐 <b>Веб-панель</b>\n\n"
            "Управляйте файлами через браузер: просмотр, скачивание, удаление, ZIP.\n\n"
            f"🔗 Ссылка (действует 2 часа):\n<code>{url}</code>\n\n"
            f"🌍 Домен: <code>{config.WEB_BASE_URL}</code>"
        ),
        reply_markup=get_settings_keyboard(_get_user_settings(message.from_user.id)["notifications"]),
        parse_mode="HTML",
    )


@db.message(F.text == "👤 Мой профиль")
async def profile_handler(message: Message):
    user = message.from_user
    files = _get_user_files(user.id)
    used = _get_used_storage(user.id)
    links_count = len(_user_links(user.id))
    username_line = f"Username: @{user.username}\n" if user.username else ""

    await message.answer(
        text=(
            "👤 <b>Мой профиль</b>\n\n"
            f"Имя: {user.full_name}\n"
            f"{username_line}"
            f"ID: <code>{user.id}</code>\n\n"
            f"📁 Файлов: <b>{len(files)}</b>\n"
            f"🔗 Публичных ссылок: <b>{links_count}</b>\n"
            f"💾 Занято: <b>{_format_size(used)}</b> / {_format_size(STORAGE_LIMIT)}"
        ),
        reply_markup=get_settings_keyboard(_get_user_settings(user.id)["notifications"]),
        parse_mode="HTML",
    )


@db.message(F.text == "💾 Использование хранилища")
async def storage_usage_handler(message: Message):
    used = _get_used_storage(message.from_user.id)
    free = max(STORAGE_LIMIT - used, 0)
    percent = used * 100 // STORAGE_LIMIT if STORAGE_LIMIT else 0
    files = _get_user_files(message.from_user.id)

    if files:
        largest = max(files, key=lambda f: f["size"])
        top_line = f"\n📦 Самый большой: <b>{largest['name']}</b> ({_format_size(largest['size'])})"
    else:
        top_line = ""

    await message.answer(
        text=(
            "💾 <b>Использование хранилища</b>\n\n"
            f"{_storage_bar(used, STORAGE_LIMIT)} {percent}%\n\n"
            f"Занято: <b>{_format_size(used)}</b>\n"
            f"Свободно: <b>{_format_size(free)}</b>\n"
            f"Лимит: <b>{_format_size(STORAGE_LIMIT)}</b>"
            f"{top_line}"
        ),
        reply_markup=get_settings_keyboard(_get_user_settings(message.from_user.id)["notifications"]),
        parse_mode="HTML",
    )


@db.message(F.text.in_({"🔔 Вкл. уведомления", "🔕 Выкл. уведомления"}))
async def toggle_notifications_handler(message: Message):
    settings = _get_user_settings(message.from_user.id)
    settings["notifications"] = not settings["notifications"]
    status = "включены" if settings["notifications"] else "выключены"
    await message.answer(
        f"🔔 Уведомления {status}.",
        reply_markup=get_settings_keyboard(settings["notifications"]),
    )


@db.message(F.text == "🗑️ Очистить все файлы")
async def clear_files_start_handler(message: Message, state: FSMContext):
    files = _get_user_files(message.from_user.id)
    if not files:
        await message.answer(
            "У вас нет файлов для удаления.",
            reply_markup=get_settings_keyboard(_get_user_settings(message.from_user.id)["notifications"]),
        )
        return

    await state.set_state(SettingsStates.confirming_clear)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить всё", callback_data="settings_clear_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="settings_clear_no"),
    )
    await message.answer(
        f"⚠️ Удалить все <b>{len(files)}</b> файлов ({_format_size(_get_used_storage(message.from_user.id))})?\n"
        "Это действие необратимо. Публичные ссылки тоже будут удалены.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@db.callback_query(F.data == "settings_clear_yes")
async def clear_files_confirm_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    files = _get_user_files(user_id)
    count = len(files)

    for file in files:
        for path_str in [file["path"], *[v["path"] for v in file.get("versions", [])]]:
            path = Path(path_str)
            if path.exists():
                path.unlink()

    files.clear()
    tokens = [t for t, l in PUBLIC_LINKS.items() if l["user_id"] == user_id]
    for token in tokens:
        PUBLIC_LINKS.pop(token, None)

    user_dir = _get_user_dir(user_id)
    if user_dir.exists():
        for item in user_dir.glob("cloud_export_*.zip"):
            item.unlink(missing_ok=True)
        if not any(user_dir.iterdir()):
            user_dir.rmdir()

    storage.persist_user(user_id)

    await state.clear()
    settings = _get_user_settings(user_id)
    await callback.message.edit_text(f"✅ Удалено файлов: <b>{count}</b>", parse_mode="HTML")
    await callback.message.answer(
        "Хранилище очищено.",
        reply_markup=get_settings_keyboard(settings["notifications"]),
    )
    await callback.answer()


@db.callback_query(F.data == "settings_clear_no")
async def clear_files_cancel_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    settings = _get_user_settings(callback.from_user.id)
    await callback.message.edit_text("❌ Очистка отменена.")
    await callback.message.answer(
        "Настройки:",
        reply_markup=get_settings_keyboard(settings["notifications"]),
    )
    await callback.answer()


# --- Публичные ссылки (скачивание) ---

async def _handle_share_link(message: Message, token: str, state: FSMContext) -> None:
    link = PUBLIC_LINKS.get(token)
    if not link:
        await message.answer("❌ Ссылка не найдена или была удалена.", reply_markup=get_main_keboard())
        return

    expires_at = link.get("expires_at")
    if expires_at and expires_at < datetime.now():
        PUBLIC_LINKS.pop(token, None)
        await message.answer("❌ Срок действия ссылки истёк.", reply_markup=get_main_keboard())
        return

    owner_file = None
    for file in _get_user_files(link["user_id"]):
        if file["id"] == link["file_id"]:
            owner_file = file
            break

    if not owner_file:
        await message.answer("❌ Файл больше не доступен.", reply_markup=get_main_keboard())
        return

    if link.get("password_hash"):
        await state.update_data(share_token=token)
        await state.set_state(ShareLinkStates.entering_password)
        await message.answer(
            f"🔒 Файл <b>{link['file_name']}</b> защищён паролем.\nВведите пароль:",
            parse_mode="HTML",
        )
        return

    await _send_shared_file(message, token, link, owner_file)


async def _send_shared_file(message: Message, token: str, link: dict, file: dict) -> None:
    path = Path(file["path"])
    if not path.exists():
        await message.answer("❌ Файл отсутствует на сервере.", reply_markup=get_main_keboard())
        return

    link["downloads"] = link.get("downloads", 0) + 1
    await message.answer(
        f"📥 <b>{file['name']}</b>\n"
        f"📦 {_format_size(file['size'])}",
        parse_mode="HTML",
    )
    await message.answer_document(FSInputFile(path, filename=file["name"]), reply_markup=get_main_keboard())


@db.message(ShareLinkStates.entering_password, F.text)
async def share_password_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("share_token")
    link = PUBLIC_LINKS.get(token)
    if not link:
        await state.clear()
        await message.answer("❌ Ссылка недействительна.", reply_markup=get_main_keboard())
        return

    if _hash_password(message.text.strip()) != link.get("password_hash"):
        await message.answer("❌ Неверный пароль. Попробуйте снова или нажмите /start.")
        return

    owner_file = _find_file(link["user_id"], link["file_id"])
    if not owner_file:
        await state.clear()
        await message.answer("❌ Файл больше не доступен.", reply_markup=get_main_keboard())
        return

    await state.clear()
    await _send_shared_file(message, token, link, owner_file)


# --- Веб-панель ---

def _web_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Облачный</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #0f1115; color: #eef2ff; }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 24px; }}
    .card {{ background: #171a21; border: 1px solid #2a3140; border-radius: 16px; padding: 20px; margin-bottom: 16px; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid #2a3140; text-align: left; }}
    a {{ color: #8ab4ff; text-decoration: none; }}
    .btn {{ display: inline-block; background: #2563eb; color: white; border-radius: 10px; padding: 10px 14px; }}
    .muted {{ color: #94a3b8; }}
    .bar {{ height: 10px; background: #2a3140; border-radius: 999px; overflow: hidden; margin: 8px 0 16px; }}
    .bar > span {{ display: block; height: 100%; background: linear-gradient(90deg, #2563eb, #38bdf8); }}
  </style>
</head>
<body><div class="wrap">{body}</div></body>
</html>"""


def _web_require_session(request: web.Request) -> tuple[str | None, dict | None]:
    token = request.query.get("token") or request.cookies.get("cloud_token")
    if not token:
        return None, None
    session = storage.get_web_session(token)
    if not session:
        return token, None
    return token, session


async def _web_index_handler(request: web.Request) -> web.Response:
    token, session = _web_require_session(request)
    if not session:
        body = """
        <div class="card">
          <h1>Облачный — веб-панель</h1>
          <p class="muted">Получите ссылку для входа в боте: ⚙️ Настройки → 🌐 Веб-панель</p>
          <p>Ссылка действует 2 часа и привязана к вашему Telegram-аккаунту.</p>
        </div>"""
        return web.Response(text=_web_page("Вход", body), content_type="text/html")

    user_id = session["user_id"]
    files = storage.get_user_files(user_id)
    used = storage.get_used_storage(user_id)
    percent = min(used * 100 // storage.STORAGE_LIMIT, 100) if storage.STORAGE_LIMIT else 0

    rows = []
    for file in files:
        versions = len(file.get("versions", []))
        version_line = f"+{versions} верс." if versions else "—"
        rows.append(
            f"<tr>"
            f"<td>{file['name']}</td>"
            f"<td>{storage.format_size(file['size'])}</td>"
            f"<td>{version_line}</td>"
            f"<td><a href='/download?token={token}&file_id={file['id']}'>Скачать</a></td>"
            f"<td><a href='/delete?token={token}&file_id={file['id']}' onclick=\"return confirm('Удалить файл?')\">Удалить</a></td>"
            f"</tr>"
        )

    table = (
        "<table><tr><th>Файл</th><th>Размер</th><th>Версии</th><th></th><th></th></tr>"
        + "".join(rows)
        + "</table>"
        if rows
        else "<p class='muted'>Файлов пока нет. Загрузите их через Telegram-бота.</p>"
    )

    body = f"""
    <div class="card">
      <h1>🌐 Веб-панель</h1>
      <p class="muted">Пользователь ID: {user_id}</p>
      <div class="bar"><span style="width:{percent}%"></span></div>
      <p>Занято: <b>{storage.format_size(used)}</b> / {storage.format_size(storage.STORAGE_LIMIT)} · Файлов: <b>{len(files)}</b></p>
    </div>
    <div class="card">
      <h2>Файлы</h2>
      {table}
    </div>
    <div class="card">
      <a class="btn" href="/download-all?token={token}">📦 Скачать всё ZIP</a>
    </div>
    """
    response = web.Response(text=_web_page("Панель", body), content_type="text/html")
    response.set_cookie("cloud_token", token, max_age=7200, httponly=True)
    return response


async def _web_download_handler(request: web.Request) -> web.Response:
    _, session = _web_require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла. Получите новую ссылку в боте.")

    file = storage.find_file(session["user_id"], request.query.get("file_id", ""))
    if not file:
        raise web.HTTPNotFound(text="Файл не найден")

    path = Path(file["path"])
    if not path.exists():
        raise web.HTTPNotFound(text="Файл отсутствует на сервере")

    return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{file["name"]}"'})


async def _web_download_all_handler(request: web.Request) -> web.Response:
    _, session = _web_require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    zip_path = storage.create_user_zip(session["user_id"])
    if not zip_path:
        raise web.HTTPNotFound(text="Нет файлов для архивации")

    return web.FileResponse(zip_path, headers={"Content-Disposition": 'attachment; filename="cloud_files.zip"'})


async def _web_delete_handler(request: web.Request) -> web.Response:
    token, session = _web_require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    file_id = request.query.get("file_id", "")
    if not storage.delete_file_record(session["user_id"], file_id):
        raise web.HTTPNotFound(text="Файл не найден")

    raise web.HTTPFound(location=f"/?token={token}")


def _create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _web_index_handler)
    app.router.add_get("/download", _web_download_handler)
    app.router.add_get("/download-all", _web_download_all_handler)
    app.router.add_get("/delete", _web_delete_handler)
    return app


async def start_web_panel(host: str, port: int) -> None:
    app = _create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()


async def main() -> None:
    await start_web_panel(config.WEB_HOST, config.WEB_PORT)
    logger.info("Веб-панель: %s", config.WEB_BASE_URL)

    try:
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                me = await bot.get_me()
                logger.info("Telegram подключён: @%s — запуск polling", me.username)
                await db.start_polling(bot)
                return
            except Exception as exc:
                logger.error("Telegram недоступен: %s", exc)
                logger.error("Диагностика: bash deploy/check-telegram.sh")
                logger.error("Решение: добавьте в .env → TELEGRAM_PROXY=socks5://IP:1080")
                await asyncio.sleep(30)
    finally:
        await bot.session.close()


def acquire_single_instance_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "❌ Уже запущен другой экземпляр бота.\n"
            "Остановите его командой: pkill -f \"bot.py\"\n"
            "Затем запустите снова."
        )
        sys.exit(1)
    lock_handle.write(str(os.getpid()))
    lock_handle.flush()
    return lock_handle


if __name__ == "__main__":
    _lock = acquire_single_instance_lock()
    asyncio.run(main())
