"""Веб-панель «Облачный» — адаптивный интерфейс для мобильных и десктопа."""

import html
import json
from datetime import datetime
from pathlib import Path

from urllib.parse import urlparse

import config
import storage
from docs_content import docs_html
from aiohttp import web

_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _docs_host() -> str:
    return urlparse(config.DOCS_BASE_URL).netloc.split(":")[0].lower()


def _is_docs_host(request: web.Request) -> bool:
    host = request.host.split(":")[0].lower()
    return host == _docs_host()


def _require_session(request: web.Request) -> tuple[str | None, dict | None]:
    token = request.query.get("token") or request.cookies.get("cloud_token")
    if not token:
        return None, None
    session = storage.get_web_session(token)
    if not session:
        return token, None
    return token, session


async def _require_session_post(request: web.Request) -> tuple[str | None, dict | None]:
    token = None
    if request.content_type == "application/json":
        try:
            data = await request.json()
            token = data.get("token")
        except Exception:
            pass
    token = token or request.cookies.get("cloud_token")
    if not token:
        return None, None
    session = storage.get_web_session(token)
    return token, session


def _public_link_url(link_token: str) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start=share_{link_token}"


def _serialize_files(user_id: int) -> list[dict]:
    items = []
    for file in storage.get_user_files(user_id):
        uploaded = file.get("uploaded_at")
        if isinstance(uploaded, datetime):
            uploaded_iso = uploaded.isoformat()
            uploaded_fmt = storage.format_datetime(uploaded)
        else:
            uploaded_iso = ""
            uploaded_fmt = "—"
        ext = Path(file["name"]).suffix.lower()
        items.append(
            {
                "id": file["id"],
                "name": file["name"],
                "size": file["size"],
                "size_fmt": storage.format_size(file["size"]),
                "icon": storage.file_icon(file["name"]),
                "category": storage.get_file_category(file["name"]),
                "versions": len(file.get("versions", [])),
                "current_version": file.get("current_version", 1),
                "uploaded_at": uploaded_iso,
                "uploaded_fmt": uploaded_fmt,
                "preview": ext in _IMAGE_EXT,
            }
        )
    return items


def _serialize_links(user_id: int) -> list[dict]:
    items = []
    now = datetime.now()
    for link_token, link in storage.get_user_links(user_id):
        expires = link.get("expires_at")
        expired = bool(expires and expires < now)
        items.append(
            {
                "token": link_token,
                "file_name": link.get("file_name", "—"),
                "url": _public_link_url(link_token),
                "has_password": bool(link.get("password_hash")),
                "downloads": link.get("downloads", 0),
                "expires_fmt": storage.format_datetime(expires) if expires else "бессрочно",
                "created_fmt": storage.format_datetime(link.get("created_at")),
                "expired": expired,
            }
        )
    return items


def _storage_stats(user_id: int) -> dict:
    used = storage.get_used_storage(user_id)
    limit = storage.STORAGE_LIMIT
    files = storage.get_user_files(user_id)
    by_category: dict[str, int] = {}
    for file in files:
        cat = storage.get_file_category(file["name"])
        by_category[cat] = by_category.get(cat, 0) + file["size"]
        for version in file.get("versions", []):
            by_category[cat] = by_category.get(cat, 0) + version["size"]
    return {
        "used": used,
        "used_fmt": storage.format_size(used),
        "limit_fmt": storage.format_size(limit),
        "free_fmt": storage.format_size(max(limit - used, 0)),
        "percent": min(used * 100 // limit, 100) if limit else 0,
        "files_count": len(files),
        "links_count": len(storage.get_user_links(user_id)),
        "by_category": {k: storage.format_size(v) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
    }


def _login_page() -> str:
    bot = f"https://t.me/{config.BOT_USERNAME}"
    docs = config.DOCS_BASE_URL
    body = f"""
    <nav class="portal-nav">
      <span class="brand">☁️ Облачный</span>
      <a href="{docs}">📖 Документация</a>
      <a href="{bot}">Telegram</a>
    </nav>
    <div class="hero">
      <div class="logo">☁️</div>
      <h1>Облачный</h1>
      <p class="muted">Личное хранилище в Telegram + веб-панель</p>
      <a class="btn btn-primary" href="{bot}">Открыть бота</a>
    </div>
    <div class="card">
      <h2>🌐 Войти в веб-панель</h2>
      <ol class="steps">
        <li>Откройте бота в Telegram</li>
        <li><b>⚙️ Настройки → 🌐 Веб-панель</b></li>
        <li>Перейдите по персональной ссылке (2 часа)</li>
      </ol>
      <p class="muted">Панель не требует пароля — доступ только по ссылке из бота.</p>
    </div>
    <div class="card">
      <h2>📖 Документация</h2>
      <p>Инструкции по загрузке файлов, ссылкам, inline-режиму и FAQ.</p>
      <a class="btn btn-ghost" href="{docs}">Читать на {docs.replace('https://', '')} →</a>
    </div>"""
    return _page("Портал", body, token=None, portal=True)


def _docs_page() -> str:
    bot = f"https://t.me/{config.BOT_USERNAME}"
    panel = config.WEB_BASE_URL
    body = f"""
    <nav class="portal-nav">
      <span class="brand">☁️ Облачный — Docs</span>
      <a href="{panel}">🌐 Панель</a>
      <a href="{bot}">Telegram</a>
    </nav>
    {docs_html(compact=False)}"""
    return _page("Документация", body, token=None, portal=True)


def _page(title: str, body: str, token: str | None, extra_head: str = "", extra_script: str = "", portal: bool = False) -> str:
    token_attr = f'data-token="{token}"' if token else ""
    portal_cls = " portal" if portal else ""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0b0f19">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <title>{title} — Облачный</title>
  <style>{_CSS}</style>
  {extra_head}
</head>
<body class="app-root{portal_cls}" {token_attr}>
  <div id="toast" class="toast" hidden></div>
  <div class="app">{body}</div>
  <script>{_JS}</script>
  {extra_script}
</body>
</html>"""


_CSS = """
:root {
  --bg: #0b0f19;
  --surface: #141925;
  --surface2: #1c2333;
  --border: #2a3347;
  --text: #eef2ff;
  --muted: #94a3b8;
  --accent: #3b82f6;
  --accent2: #06b6d4;
  --danger: #ef4444;
  --ok: #22c55e;
  --radius: 14px;
  --nav-h: 64px;
  --safe-b: env(safe-area-inset-bottom, 0px);
}
* { box-sizing: border-box; }
html, body { margin: 0; min-height: 100%; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; }
a { color: var(--accent); text-decoration: none; }
.app { max-width: 960px; margin: 0 auto; padding: 16px 16px calc(var(--nav-h) + var(--safe-b) + 16px); }
@media (min-width: 769px) {
  .app { padding-bottom: 24px; }
  .bottom-nav { display: none !important; }
  .sidebar-nav { display: flex !important; }
}
.hero { text-align: center; padding: 32px 0 16px; }
.logo { font-size: 48px; line-height: 1; }
h1 { font-size: 1.75rem; margin: 8px 0; }
h2 { font-size: 1.1rem; margin: 0 0 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px; margin-bottom: 12px; }
.muted { color: var(--muted); font-size: 0.9rem; }
.steps { margin: 0; padding-left: 20px; line-height: 1.8; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 16px; flex-wrap: wrap; }
.topbar h1 { margin: 0; font-size: 1.25rem; }
.storage-mini { flex: 1; min-width: 140px; }
.bar { height: 8px; background: var(--surface2); border-radius: 999px; overflow: hidden; margin-top: 6px; }
.bar > span { display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .3s; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center; }
.search { flex: 1; min-width: 160px; padding: 10px 14px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text); font-size: 16px; }
.search:focus { outline: 2px solid var(--accent); border-color: transparent; }
select.sort, .chip { padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text); font-size: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.chip { cursor: pointer; user-select: none; transition: .15s; }
.chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.view-toggle { display: flex; gap: 4px; }
.view-btn { width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text); cursor: pointer; font-size: 16px; }
.view-btn.active { background: var(--accent); border-color: var(--accent); }
.file-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
@media (min-width: 480px) { .file-grid { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 769px) { .file-grid.cols-list { display: block; } }
.file-card { background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px; display: flex; flex-direction: column; gap: 8px; transition: border-color .15s; }
.file-card:hover { border-color: var(--accent); }
.file-card.hidden { display: none !important; }
.file-head { display: flex; gap: 10px; align-items: flex-start; }
.file-icon { font-size: 28px; line-height: 1; flex-shrink: 0; }
.file-name { font-weight: 600; word-break: break-word; font-size: 0.95rem; }
.file-meta { font-size: 0.8rem; color: var(--muted); }
.file-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  padding: 8px 12px; border-radius: 10px; border: none; font-size: 0.85rem; font-weight: 600;
  cursor: pointer; text-decoration: none; min-height: 40px; transition: .15s; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text); }
.btn-danger { background: rgba(239,68,68,.15); color: #fca5a5; border: 1px solid rgba(239,68,68,.3); }
.btn-sm { padding: 6px 10px; min-height: 34px; font-size: 0.8rem; }
.btn:active { transform: scale(.97); }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table.files-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
table.files-table th, table.files-table td { padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; }
table.files-table th { color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
table.files-table tr.hidden { display: none; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
.link-item { padding: 12px 0; border-bottom: 1px solid var(--border); }
.link-item:last-child { border-bottom: none; }
.link-url { font-size: 0.8rem; word-break: break-all; color: var(--muted); margin: 6px 0; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 600; }
.badge-ok { background: rgba(34,197,94,.15); color: #86efac; }
.badge-warn { background: rgba(234,179,8,.15); color: #fde047; }
.badge-lock { background: rgba(148,163,184,.15); color: #cbd5e1; }
.stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
@media (min-width: 480px) { .stat-grid { grid-template-columns: repeat(4, 1fr); } }
.stat-box { background: var(--surface2); border-radius: 12px; padding: 14px; text-align: center; }
.stat-val { font-size: 1.4rem; font-weight: 700; }
.stat-label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
.cat-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
.bottom-nav { position: fixed; left: 0; right: 0; bottom: 0; height: calc(var(--nav-h) + var(--safe-b));
  padding-bottom: var(--safe-b); background: var(--surface); border-top: 1px solid var(--border);
  display: flex; z-index: 100; }
.nav-item { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; color: var(--muted); font-size: 0.65rem; cursor: pointer; border: none; background: none;
  padding: 8px 0; -webkit-tap-highlight-color: transparent; }
.nav-item .ico { font-size: 1.35rem; }
.nav-item.active { color: var(--accent); }
.sidebar-nav { display: none; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.sidebar-nav .nav-item { flex: unset; flex-direction: row; font-size: 0.9rem; padding: 10px 16px;
  border-radius: 10px; border: 1px solid var(--border); background: var(--surface2); }
.sidebar-nav .nav-item.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.empty { text-align: center; padding: 32px 16px; color: var(--muted); }
.empty-icon { font-size: 48px; margin-bottom: 8px; }
.fab-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.85); z-index: 200; display: flex;
  align-items: center; justify-content: center; padding: 16px; }
.modal[hidden] { display: none; }
.modal img { max-width: 100%; max-height: 85vh; border-radius: 12px; }
.modal-close { position: absolute; top: 16px; right: 16px; width: 44px; height: 44px; border-radius: 50%;
  border: none; background: var(--surface2); color: #fff; font-size: 20px; cursor: pointer; }
.toast { position: fixed; bottom: calc(var(--nav-h) + var(--safe-b) + 12px); left: 50%; transform: translateX(-50%);
  background: var(--surface2); border: 1px solid var(--border); padding: 10px 20px; border-radius: 999px;
  font-size: 0.9rem; z-index: 300; box-shadow: 0 8px 32px rgba(0,0,0,.4); white-space: nowrap; }
@media (min-width: 769px) { .toast { bottom: 24px; } }
body.portal .app { padding-bottom: 24px; }
.portal-nav { display: flex; gap: 12px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
.portal-nav .brand { font-weight: 700; font-size: 1.05rem; margin-right: auto; color: var(--text); }
.portal-nav a { color: var(--muted); font-size: 0.9rem; }
.portal-nav a.active { color: var(--accent); }
.doc-section p { margin: 8px 0; line-height: 1.65; }
.doc-section ul.steps { list-style: disc; }
.doc-section code { background: var(--surface2); padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }
"""


_JS = """
function $(s,r=document){return r.querySelector(s);}
function $$(s,r=document){return [...r.querySelectorAll(s)];}
function toast(msg){
  const t=$('#toast'); if(!t)return;
  t.textContent=msg; t.hidden=false;
  clearTimeout(toast._t); toast._t=setTimeout(()=>t.hidden=true,2500);
}
async function apiPost(path, body){
  const token=document.body.dataset.token;
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({...body,token})});
  if(!r.ok){const e=await r.text();throw new Error(e||r.statusText);}
  return r.json();
}
function switchTab(name){
  $$('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tab===name));
  $$('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));
  localStorage.setItem('cloud_tab',name);
}
function initTabs(){
  const saved=localStorage.getItem('cloud_tab')||'files';
  switchTab(saved);
  $$('.nav-item').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.tab)));
}
function filterFiles(){
  const q=($('#search')?.value||'').toLowerCase();
  const cat=$('.chip.active')?.dataset.cat||'all';
  const sort=$('#sort')?.value||'date-desc';
  let items=[...$$('.file-card, .files-table tbody tr')];
  items.forEach(el=>{
    const name=(el.dataset.name||'').toLowerCase();
    const c=el.dataset.cat||'';
    const ok=(!q||name.includes(q))&&(cat==='all'||c===cat);
    el.classList.toggle('hidden',!ok);
  });
  const grid=$('#file-grid');
  if(!grid)return;
  const cards=[...grid.querySelectorAll('.file-card:not(.hidden)')];
  cards.sort((a,b)=>{
    if(sort==='name') return a.dataset.name.localeCompare(b.dataset.name,'ru');
    if(sort==='size') return +b.dataset.size - +a.dataset.size;
    if(sort==='date') return (b.dataset.date||'').localeCompare(a.dataset.date||'');
    return (b.dataset.date||'').localeCompare(a.dataset.date||'');
  });
  cards.forEach(c=>grid.appendChild(c));
}
function initFilters(){
  $('#search')?.addEventListener('input',filterFiles);
  $('#sort')?.addEventListener('change',filterFiles);
  $$('.chip').forEach(c=>c.addEventListener('click',()=>{
    $$('.chip').forEach(x=>x.classList.remove('active'));
    c.classList.add('active'); filterFiles();
  }));
}
function setView(mode){
  const grid=$('#file-grid'); if(!grid)return;
  grid.classList.toggle('cols-list',mode==='list');
  $$('.view-btn').forEach(b=>b.classList.toggle('active',b.dataset.view===mode));
  localStorage.setItem('cloud_view',mode);
  const table=$('#file-table'); if(table) table.hidden=(mode!=='list');
  grid.hidden=(mode==='list');
}
function initView(){
  const v=localStorage.getItem('cloud_view')|| (window.innerWidth>=769?'list':'grid');
  setView(v);
  $$('.view-btn').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
}
async function deleteFile(id, name){
  if(!confirm('Удалить «'+name+'»?'))return;
  try{
    await apiPost('/api/delete',{file_id:id});
    toast('Файл удалён');
    location.reload();
  }catch(e){toast('Ошибка: '+e.message);}
}
async function deleteLink(token){
  if(!confirm('Удалить публичную ссылку?'))return;
  try{
    await apiPost('/api/delete-link',{link_token:token});
    toast('Ссылка удалена');
    location.reload();
  }catch(e){toast('Ошибка: '+e.message);}
}
function copyText(text){
  navigator.clipboard.writeText(text).then(()=>toast('Скопировано')).catch(()=>{
    const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy'); ta.remove(); toast('Скопировано');
  });
}
function previewImg(url){
  const m=$('#modal'); const img=$('#modal-img');
  if(!m||!img)return;
  img.src=url; m.hidden=false;
}
function initModal(){
  $('#modal')?.addEventListener('click',e=>{
    if(e.target.id==='modal'||e.target.classList.contains('modal-close')) $('#modal').hidden=true;
  });
}
document.addEventListener('DOMContentLoaded',()=>{
  initTabs(); initFilters(); initView(); initModal();
  window.deleteFile=deleteFile; window.deleteLink=deleteLink;
  window.copyText=copyText; window.previewImg=previewImg;
});
"""


def _dashboard_page(token: str, user_id: int) -> str:
    stats = _storage_stats(user_id)
    files = _serialize_files(user_id)
    links = _serialize_links(user_id)

    cards_html = ""
    for f in files:
        safe_name = json.dumps(f["name"])
        preview_btn = (
            f'<button class="btn btn-ghost btn-sm" onclick="previewImg(\'/preview?token={token}&file_id={f["id"]}\')">👁</button>'
            if f["preview"]
            else ""
        )
        ver = f'+{f["versions"]} ver.' if f["versions"] else ""
        cards_html += f"""
        <article class="file-card" data-name="{html.escape(f['name'])}" data-cat="{f['category']}"
                 data-size="{f['size']}" data-date="{f['uploaded_at']}">
          <div class="file-head">
            <span class="file-icon">{f['icon']}</span>
            <div>
              <div class="file-name">{html.escape(f['name'])}</div>
              <div class="file-meta">{f['size_fmt']} · {f['uploaded_fmt']} {ver}</div>
            </div>
          </div>
          <div class="file-actions">
            <a class="btn btn-primary btn-sm" href="/download?token={token}&file_id={f['id']}">⬇️ Скачать</a>
            {preview_btn}
            <button class="btn btn-danger btn-sm" onclick="deleteFile('{f['id']}', {safe_name})">🗑</button>
          </div>
        </article>"""

    table_rows = ""
    for f in files:
        safe_name = json.dumps(f["name"])
        table_rows += f"""
        <tr data-name="{html.escape(f['name'])}" data-cat="{f['category']}" data-size="{f['size']}" data-date="{f['uploaded_at']}">
          <td>{f['icon']} {html.escape(f['name'])}</td>
          <td>{f['size_fmt']}</td>
          <td>{f['uploaded_fmt']}</td>
          <td>
            <a href="/download?token={token}&file_id={f['id']}">⬇️</a>
            <button class="btn btn-danger btn-sm" onclick="deleteFile('{f['id']}', {safe_name})">🗑</button>
          </td>
        </tr>"""

    files_empty = '<div class="empty"><div class="empty-icon">📭</div><p>Файлов нет</p><p class="muted">Загрузите через Telegram-бота</p></div>'
    files_content = cards_html if files else files_empty

    links_html = ""
    for link in links:
        status = '<span class="badge badge-warn">истекла</span>' if link["expired"] else '<span class="badge badge-ok">активна</span>'
        lock = '<span class="badge badge-lock">🔒 пароль</span>' if link["has_password"] else ""
        links_html += f"""
        <div class="link-item">
          <div><strong>{link['file_name']}</strong> {status} {lock}</div>
          <div class="link-url">{link['url']}</div>
          <div class="file-meta">До: {link['expires_fmt']} · Скачиваний: {link['downloads']}</div>
          <div class="file-actions" style="margin-top:8px">
            <button class="btn btn-ghost btn-sm" onclick="copyText('{link['url']}')">📋 Копировать</button>
            <button class="btn btn-danger btn-sm" onclick="deleteLink('{link['token']}')">🗑</button>
          </div>
        </div>"""
    links_content = links_html if links else '<div class="empty"><div class="empty-icon">🔗</div><p>Нет публичных ссылок</p></div>'

    cat_rows = "".join(
        f'<div class="cat-row"><span>{storage.file_icon(k)} {k}</span><span>{v}</span></div>'
        for k, v in stats["by_category"].items()
    ) or '<p class="muted">Нет данных</p>'

    body = f"""
    <div class="topbar">
      <h1>☁️ Облачный</h1>
      <div class="storage-mini">
        <div class="muted" style="font-size:.75rem">{stats['used_fmt']} / {stats['limit_fmt']}</div>
        <div class="bar"><span style="width:{stats['percent']}%"></span></div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <button class="nav-item active" data-tab="files">📁 Файлы</button>
      <button class="nav-item" data-tab="links">🔗 Ссылки</button>
      <button class="nav-item" data-tab="stats">📊 Статистика</button>
      <button class="nav-item" data-tab="help">📖 Справка</button>
    </nav>

    <div class="tab-panel active" data-tab="files">
      <div class="fab-row">
        <a class="btn btn-primary" href="/download-all?token={token}">📦 ZIP всё</a>
      </div>
      <div class="toolbar">
        <input class="search" id="search" type="search" placeholder="🔍 Поиск файлов..." autocomplete="off">
        <select class="sort" id="sort">
          <option value="date-desc">Новые первые</option>
          <option value="name">По имени</option>
          <option value="size">По размеру</option>
        </select>
        <div class="view-toggle">
          <button class="view-btn active" data-view="grid" title="Сетка">▦</button>
          <button class="view-btn" data-view="list" title="Список">☰</button>
        </div>
      </div>
      <div class="chips">
        <span class="chip active" data-cat="all">Все</span>
        <span class="chip" data-cat="image">🖼️</span>
        <span class="chip" data-cat="doc">📄</span>
        <span class="chip" data-cat="video">🎬</span>
        <span class="chip" data-cat="audio">🎵</span>
        <span class="chip" data-cat="archive">📦</span>
        <span class="chip" data-cat="code">💻</span>
      </div>
      <div id="file-grid" class="file-grid">{files_content}</div>
      <div id="file-table" class="table-wrap" hidden>
        <table class="files-table"><thead><tr><th>Файл</th><th>Размер</th><th>Дата</th><th></th></tr></thead>
        <tbody>{table_rows}</tbody></table>
      </div>
    </div>

    <div class="tab-panel" data-tab="links">
      <div class="card"><h2>Публичные ссылки</h2>{links_content}</div>
    </div>

    <div class="tab-panel" data-tab="stats">
      <div class="stat-grid">
        <div class="stat-box"><div class="stat-val">{stats['files_count']}</div><div class="stat-label">Файлов</div></div>
        <div class="stat-box"><div class="stat-val">{stats['links_count']}</div><div class="stat-label">Ссылок</div></div>
        <div class="stat-box"><div class="stat-val">{stats['percent']}%</div><div class="stat-label">Занято</div></div>
        <div class="stat-box"><div class="stat-val">{stats['free_fmt']}</div><div class="stat-label">Свободно</div></div>
      </div>
      <div class="card" style="margin-top:12px"><h2>По типам</h2>{cat_rows}</div>
    </div>

    <div class="tab-panel" data-tab="help">
      {docs_html(compact=True)}
      <p style="margin-top:12px"><a href="{config.DOCS_BASE_URL}" target="_blank" rel="noopener">Полная документация →</a></p>
    </div>

    <nav class="bottom-nav">
      <button class="nav-item active" data-tab="files"><span class="ico">📁</span>Файлы</button>
      <button class="nav-item" data-tab="links"><span class="ico">🔗</span>Ссылки</button>
      <button class="nav-item" data-tab="stats"><span class="ico">📊</span>Стат</button>
      <button class="nav-item" data-tab="help"><span class="ico">📖</span>Справка</button>
    </nav>

    <div id="modal" class="modal" hidden>
      <button class="modal-close">✕</button>
      <img id="modal-img" alt="preview">
    </div>
    """
    return _page("Панель", body, token)


async def docs_handler(request: web.Request) -> web.Response:
    raise web.HTTPFound(location=config.DOCS_BASE_URL)


async def index_handler(request: web.Request) -> web.Response:
    if _is_docs_host(request):
        return web.Response(text=_docs_page(), content_type="text/html")

    token, session = _require_session(request)
    if not session:
        return web.Response(text=_login_page(), content_type="text/html")

    html = _dashboard_page(token, session["user_id"])
    response = web.Response(text=html, content_type="text/html")
    response.set_cookie("cloud_token", token, max_age=7200, httponly=True, samesite="Lax")
    return response


async def download_handler(request: web.Request) -> web.Response:
    _, session = _require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла. Получите новую ссылку в боте.")

    file = storage.find_file(session["user_id"], request.query.get("file_id", ""))
    if not file:
        raise web.HTTPNotFound(text="Файл не найден")

    path = Path(file["path"])
    if not path.exists():
        raise web.HTTPNotFound(text="Файл отсутствует на сервере")

    return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{file["name"]}"'})


async def preview_handler(request: web.Request) -> web.Response:
    _, session = _require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    file = storage.find_file(session["user_id"], request.query.get("file_id", ""))
    if not file:
        raise web.HTTPNotFound(text="Файл не найден")

    path = Path(file["path"])
    if path.suffix.lower() not in _IMAGE_EXT or not path.exists():
        raise web.HTTPNotFound(text="Превью недоступно")

    return web.FileResponse(path)


async def download_all_handler(request: web.Request) -> web.Response:
    _, session = _require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    zip_path = storage.create_user_zip(session["user_id"])
    if not zip_path:
        raise web.HTTPNotFound(text="Нет файлов для архивации")

    return web.FileResponse(zip_path, headers={"Content-Disposition": 'attachment; filename="cloud_files.zip"'})


async def delete_handler(request: web.Request) -> web.Response:
    token, session = _require_session_post(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    try:
        data = await request.json()
    except Exception:
        data = {}
    file_id = data.get("file_id", "")
    if not storage.delete_file_record(session["user_id"], file_id):
        raise web.HTTPNotFound(text="Файл не найден")

    return web.json_response({"ok": True})


async def delete_link_handler(request: web.Request) -> web.Response:
    _, session = _require_session_post(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    try:
        data = await request.json()
    except Exception:
        data = {}
    link_token = data.get("link_token", "")
    if not storage.delete_public_link(session["user_id"], link_token):
        raise web.HTTPNotFound(text="Ссылка не найдена")

    return web.json_response({"ok": True})


async def delete_legacy_handler(request: web.Request) -> web.Response:
    token, session = _require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Сессия истекла.")

    file_id = request.query.get("file_id", "")
    if not storage.delete_file_record(session["user_id"], file_id):
        raise web.HTTPNotFound(text="Файл не найден")

    raise web.HTTPFound(location=f"/?token={token}")


def create_web_app() -> web.Application:
    from admin_panel import register_admin_routes

    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/docs", docs_handler)
    app.router.add_get("/download", download_handler)
    app.router.add_get("/preview", preview_handler)
    app.router.add_get("/download-all", download_all_handler)
    app.router.add_get("/delete", delete_legacy_handler)
    app.router.add_post("/api/delete", delete_handler)
    app.router.add_post("/api/delete-link", delete_link_handler)
    register_admin_routes(app)
    return app
