import json
import secrets
import shutil
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

STORAGE_LIMIT = 5 * 1024 ** 3
DATA_DIR = Path(__file__).parent / "data" / "users"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WEB_SESSIONS_FILE = Path(__file__).parent / "data" / "web_sessions.json"

USER_FILES: dict[int, list[dict]] = {}
PUBLIC_LINKS: dict[str, dict] = {}
USER_SETTINGS: dict[int, dict] = {}
LINK_DRAFTS: dict[int, dict] = {}
WEB_SESSIONS: dict[str, dict] = {}

DEFAULT_SETTINGS = {
    "notifications": True,
    "language": "ru",
}


def _meta_path(user_id: int) -> Path:
    return _get_user_dir(user_id) / "meta.json"


def _serialize_file(file: dict) -> dict:
    data = dict(file)
    uploaded_at = data.get("uploaded_at")
    if isinstance(uploaded_at, datetime):
        data["uploaded_at"] = uploaded_at.isoformat()
    versions = []
    for version in data.get("versions", []):
        item = dict(version)
        if isinstance(item.get("uploaded_at"), datetime):
            item["uploaded_at"] = item["uploaded_at"].isoformat()
        versions.append(item)
    data["versions"] = versions
    return data


def _deserialize_file(data: dict) -> dict:
    file = dict(data)
    if file.get("uploaded_at"):
        file["uploaded_at"] = datetime.fromisoformat(file["uploaded_at"])
    file["versions"] = file.get("versions", [])
    for version in file["versions"]:
        if version.get("uploaded_at"):
            version["uploaded_at"] = datetime.fromisoformat(version["uploaded_at"])
    file.setdefault("current_version", len(file["versions"]) or 1)
    return file


def _serialize_link(link: dict) -> dict:
    data = dict(link)
    for key in ("expires_at", "created_at"):
        if isinstance(data.get(key), datetime):
            data[key] = data[key].isoformat()
    return data


def _deserialize_link(data: dict) -> dict:
    link = dict(data)
    for key in ("expires_at", "created_at"):
        if link.get(key):
            link[key] = datetime.fromisoformat(link[key])
    return link


def persist_user(user_id: int) -> None:
    user_dir = _get_user_dir(user_id)
    files = [_serialize_file(f) for f in USER_FILES.get(user_id, [])]
    links = {
        token: _serialize_link(link)
        for token, link in PUBLIC_LINKS.items()
        if link["user_id"] == user_id
    }
    payload = {
        "files": files,
        "links": links,
        "settings": USER_SETTINGS.get(user_id, DEFAULT_SETTINGS.copy()),
    }
    _meta_path(user_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all_users() -> None:
    if DATA_DIR.exists():
        for user_dir in DATA_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            meta_file = user_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                user_id = int(user_dir.name)
                payload = json.loads(meta_file.read_text(encoding="utf-8"))
            except (ValueError, json.JSONDecodeError):
                continue

            USER_FILES[user_id] = [_deserialize_file(item) for item in payload.get("files", [])]
            USER_SETTINGS[user_id] = payload.get("settings", DEFAULT_SETTINGS.copy())
            for token, link_data in payload.get("links", {}).items():
                PUBLIC_LINKS[token] = _deserialize_link(link_data)
    load_web_sessions()


def load_web_sessions() -> None:
    if not WEB_SESSIONS_FILE.exists():
        return
    try:
        raw = json.loads(WEB_SESSIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for token, data in raw.items():
        session = dict(data)
        if session.get("expires_at"):
            session["expires_at"] = datetime.fromisoformat(session["expires_at"])
        WEB_SESSIONS[token] = session


def persist_web_sessions() -> None:
    WEB_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    for token, session in WEB_SESSIONS.items():
        item = dict(session)
        if isinstance(item.get("expires_at"), datetime):
            item["expires_at"] = item["expires_at"].isoformat()
        payload[token] = item
    WEB_SESSIONS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_user_dir(user_id: int) -> Path:
    path = DATA_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_user_files(user_id: int) -> list[dict]:
    return USER_FILES.setdefault(user_id, [])


def get_user_settings(user_id: int) -> dict:
    return USER_SETTINGS.setdefault(user_id, DEFAULT_SETTINGS.copy())


def find_file(user_id: int, file_id: str) -> dict | None:
    for file in get_user_files(user_id):
        if file["id"] == file_id:
            return file
    return None


def get_user_links(user_id: int) -> list[tuple[str, dict]]:
    return [(token, link) for token, link in PUBLIC_LINKS.items() if link["user_id"] == user_id]


def delete_public_link(user_id: int, link_token: str) -> bool:
    link = PUBLIC_LINKS.get(link_token)
    if not link or link["user_id"] != user_id:
        return False
    PUBLIC_LINKS.pop(link_token)
    persist_user(user_id)
    return True


def get_file_category(name: str) -> str:
    ext = Path(name).suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic"}:
        return "image"
    if ext in {"mp4", "mov", "avi", "mkv", "webm"}:
        return "video"
    if ext in {"mp3", "wav", "ogg", "flac", "aac", "m4a"}:
        return "audio"
    if ext in {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "odt"}:
        return "doc"
    if ext in {"zip", "rar", "7z", "tar", "gz", "bz2"}:
        return "archive"
    if ext in {"py", "js", "ts", "html", "css", "json", "xml", "yaml", "yml", "md", "sh"}:
        return "code"
    return "other"


def file_icon(name: str) -> str:
    icons = {
        "image": "🖼️",
        "video": "🎬",
        "audio": "🎵",
        "doc": "📄",
        "archive": "📦",
        "code": "💻",
        "other": "📁",
    }
    return icons.get(get_file_category(name), "📁")


def format_datetime(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def get_used_storage(user_id: int) -> int:
    total = 0
    for file in get_user_files(user_id):
        total += file["size"]
        for version in file.get("versions", []):
            total += version["size"]
    return total


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 ** 2:.1f} MB"


def unique_filename(user_id: int, name: str) -> str:
    existing = {f["name"].lower() for f in get_user_files(user_id)}
    if name.lower() not in existing:
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    counter = 1
    while True:
        candidate = f"{stem} ({counter}){suffix}"
        if candidate.lower() not in existing:
            return candidate
        counter += 1


def find_file_by_name(user_id: int, name: str) -> dict | None:
    lowered = name.lower()
    for file in get_user_files(user_id):
        if file["name"].lower() == lowered:
            return file
    return None


def add_file_version(user_id: int, file_id: str, new_path: Path, new_size: int, tg_file_id: str) -> dict | None:
    file = find_file(user_id, file_id)
    if not file:
        return None

    versions = file.setdefault("versions", [])
    current_version = file.get("current_version", 1)
    user_dir = _get_user_dir(user_id)
    version_dir = user_dir / "versions" / file_id
    version_dir.mkdir(parents=True, exist_ok=True)

    old_path = Path(file["path"])
    archived_path = version_dir / f"v{current_version}_{file['name']}"
    if old_path.exists():
        shutil.move(old_path, archived_path)

    versions.append(
        {
            "version": current_version,
            "path": str(archived_path),
            "size": file["size"],
            "uploaded_at": file.get("uploaded_at", datetime.now()),
            "telegram_file_id": file.get("telegram_file_id"),
        }
    )

    file["path"] = str(new_path)
    file["size"] = new_size
    file["telegram_file_id"] = tg_file_id
    file["current_version"] = current_version + 1
    file["uploaded_at"] = datetime.now()
    persist_user(user_id)
    return file


def create_user_zip(user_id: int) -> Path | None:
    files = get_user_files(user_id)
    if not files:
        return None

    zip_path = _get_user_dir(user_id) / f"cloud_export_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            path = Path(file["path"])
            if path.exists():
                archive.write(path, arcname=file["name"])
            for version in file.get("versions", []):
                vpath = Path(version["path"])
                if vpath.exists():
                    archive.write(
                        vpath,
                        arcname=f"_versions/{file['name']}/v{version['version']}_{Path(version['path']).name}",
                    )
    return zip_path


def generate_qr_bytes(url: str) -> BytesIO:
    import qrcode

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def create_web_session(user_id: int) -> str:
    """Постоянная персональная ссылка — один токен на пользователя."""
    now = datetime.now()
    for token, session in WEB_SESSIONS.items():
        if session["user_id"] != user_id:
            continue
        expires = session.get("expires_at")
        if expires and expires < now:
            continue
        if expires:
            session.pop("expires_at", None)
            persist_web_sessions()
        return token

    token = secrets.token_urlsafe(24)
    WEB_SESSIONS[token] = {"user_id": user_id}
    persist_web_sessions()
    return token


def get_web_session(token: str) -> dict | None:
    session = WEB_SESSIONS.get(token)
    if not session:
        return None
    expires_at = session.get("expires_at")
    if expires_at and expires_at < datetime.now():
        WEB_SESSIONS.pop(token, None)
        persist_web_sessions()
        return None
    return session


def remove_public_links_for_file(user_id: int, file_id: str) -> None:
    expired = [
        token
        for token, link in PUBLIC_LINKS.items()
        if link["user_id"] == user_id and link["file_id"] == file_id
    ]
    for token in expired:
        PUBLIC_LINKS.pop(token, None)
    persist_user(user_id)


def delete_file_record(user_id: int, file_id: str) -> dict | None:
    file = find_file(user_id, file_id)
    if not file:
        return None

    for path_str in [file["path"], *[v["path"] for v in file.get("versions", [])]]:
        path = Path(path_str)
        if path.exists():
            path.unlink()

    get_user_files(user_id).remove(file)
    remove_public_links_for_file(user_id, file_id)
    persist_user(user_id)
    return file


load_all_users()
