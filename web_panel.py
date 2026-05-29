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
        <li>Перейдите по персональной ссылке — она постоянная</li>
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
  --bg: #0a0e17;
  --bg2: #0f1520;
  --surface: #141925;
  --surface2: #1a2233;
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
html, body { margin: 0; min-height: 100%;
  background: var(--bg);
  background-image: radial-gradient(ellipse 80% 50% at 50% -20%, rgba(59,130,246,.12), transparent),
    radial-gradient(ellipse 60% 40% at 100% 0%, rgba(6,182,212,.08), transparent);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  -webkit-font-smoothing: antialiased; }
a { color: var(--accent); text-decoration: none; }
.app { max-width: 960px; margin: 0 auto; padding: 12px 16px calc(var(--nav-h) + var(--safe-b) + 16px); }
@media (min-width: 769px) {
  .app { padding: 20px 24px 32px; }
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

.header-card {
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%);
  border: 1px solid var(--border); border-radius: calc(var(--radius) + 2px);
  padding: 16px 18px; margin-bottom: 14px;
}
.header-top { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.header-logo {
  width: 44px; height: 44px; border-radius: 12px; flex-shrink: 0;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  display: flex; align-items: center; justify-content: center; font-size: 22px;
  box-shadow: 0 4px 16px rgba(59,130,246,.25);
}
.header-title { flex: 1; min-width: 0; }
.header-title h1 { margin: 0; font-size: 1.15rem; font-weight: 700; letter-spacing: -.02em; }
.header-sub { font-size: 0.78rem; color: var(--muted); margin-top: 2px; }
.storage-block { }
.storage-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.storage-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.storage-value { font-size: 0.85rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.bar { height: 10px; background: rgba(0,0,0,.35); border-radius: 999px; overflow: hidden; }
.bar > span {
  display: block; height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  transition: width .4s ease; min-width: 0;
  box-shadow: 0 0 12px rgba(59,130,246,.4);
}
.bar.warn > span { background: linear-gradient(90deg, #eab308, #f97316); box-shadow: 0 0 12px rgba(234,179,8,.35); }
.bar.danger > span { background: linear-gradient(90deg, #ef4444, #f97316); box-shadow: 0 0 12px rgba(239,68,68,.35); }

.files-toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; align-items: stretch;
}
.files-toolbar .search { flex: 1 1 180px; }
.toolbar-actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.search {
  padding: 10px 14px 10px 36px; border-radius: 11px; border: 1px solid var(--border);
  background: var(--surface2) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%2394a3b8' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85zm-5.242 1.156a5 5 0 1 1 0-10 5 5 0 0 1 0 10z'/%3E%3C/svg%3E") 12px center no-repeat;
  color: var(--text); font-size: 16px;
}
.search:focus { outline: 2px solid var(--accent); border-color: transparent; background-color: var(--surface); }
select.sort, .chip {
  padding: 9px 12px; border-radius: 11px; border: 1px solid var(--border);
  background: var(--surface2); color: var(--text); font-size: 14px;
}
.chips {
  display: flex; gap: 6px; margin-bottom: 12px;
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  scrollbar-width: none; padding-bottom: 2px;
}
.chips::-webkit-scrollbar { display: none; }
.chip { cursor: pointer; user-select: none; transition: .15s; white-space: nowrap; flex-shrink: 0; font-size: 13px; }
.chip:hover { border-color: var(--accent); }
.chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.view-toggle { display: flex; gap: 2px; background: var(--surface2); border-radius: 10px; padding: 3px; border: 1px solid var(--border); }
.view-btn {
  width: 34px; height: 34px; border-radius: 8px; border: none;
  background: transparent; color: var(--muted); cursor: pointer; font-size: 15px;
  transition: .15s;
}
.view-btn.active { background: var(--accent); color: #fff; }
.file-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
@media (min-width: 480px) { .file-grid { grid-template-columns: repeat(2, 1fr); } }
@media (min-width: 769px) { .file-grid.cols-list { display: block; } }
.file-card {
  background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px; display: flex; flex-direction: column; gap: 8px;
  transition: border-color .15s, transform .15s, box-shadow .15s;
}
.file-card:hover { border-color: rgba(59,130,246,.5); box-shadow: 0 4px 20px rgba(0,0,0,.25); transform: translateY(-1px); }
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
.stat-box { background: linear-gradient(145deg, var(--surface2), var(--surface)); border: 1px solid var(--border); border-radius: 12px; padding: 14px; text-align: center; }
.stat-val { font-size: 1.4rem; font-weight: 700; }
.stat-label { font-size: 0.75rem; color: var(--muted); margin-top: 4px; }
.cat-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
.bottom-nav { position: fixed; left: 0; right: 0; bottom: 0; height: calc(var(--nav-h) + var(--safe-b));
  padding-bottom: var(--safe-b); background: rgba(20,25,37,.92); backdrop-filter: blur(12px);
  border-top: 1px solid var(--border); display: flex; z-index: 100; }
.nav-item { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; color: var(--muted); font-size: 0.65rem; cursor: pointer; border: none; background: none;
  padding: 8px 0; -webkit-tap-highlight-color: transparent; }
.nav-item .ico { font-size: 1.35rem; }
.nav-item.active { color: var(--accent); }
.sidebar-nav {
  display: none; gap: 6px; margin-bottom: 14px; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 5px;
}
.sidebar-nav .nav-item {
  flex: 1; min-width: 0; flex-direction: row; font-size: 0.85rem; padding: 10px 12px;
  border-radius: 9px; border: none; background: transparent; color: var(--muted);
  justify-content: center;
}
.sidebar-nav .nav-item.active { background: var(--accent); color: #fff; box-shadow: 0 2px 8px rgba(59,130,246,.3); }
.empty {
  text-align: center; padding: 40px 20px 48px; color: var(--muted);
  grid-column: 1 / -1;
}
.empty-visual {
  width: 88px; height: 88px; margin: 0 auto 16px; border-radius: 50%;
  background: linear-gradient(145deg, rgba(59,130,246,.15), rgba(6,182,212,.08));
  border: 1px solid rgba(59,130,246,.2);
  display: flex; align-items: center; justify-content: center; font-size: 40px;
}
.empty h3 { margin: 0 0 6px; color: var(--text); font-size: 1.05rem; font-weight: 600; }
.empty p { margin: 0 0 16px; font-size: 0.9rem; line-height: 1.5; }
.empty .btn { margin-top: 4px; }
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
@media (max-width: 520px) {
  .files-toolbar { flex-direction: column; }
  .files-toolbar .toolbar-actions { width: 100%; flex-wrap: wrap; }
  .files-toolbar .search { width: 100%; }
  .toolbar-actions .sort { flex: 1; min-width: 120px; }
}
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
    bot_url = f"https://t.me/{config.BOT_USERNAME}"

    bar_cls = "bar"
    if stats["percent"] >= 90:
        bar_cls += " danger"
    elif stats["percent"] >= 70:
        bar_cls += " warn"

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

    files_empty = f"""
    <div class="empty">
      <div class="empty-visual">☁️</div>
      <h3>Облако пустое</h3>
      <p>Отправьте файл боту в Telegram —<br>он появится здесь автоматически</p>
      <a class="btn btn-primary" href="{bot_url}">Открыть @{config.BOT_USERNAME}</a>
    </div>"""
    files_content = cards_html if files else files_empty

    table_section = ""
    if files:
        table_section = f"""
      <div id="file-table" class="table-wrap" hidden>
        <table class="files-table"><thead><tr><th>Файл</th><th>Размер</th><th>Дата</th><th></th></tr></thead>
        <tbody>{table_rows}</tbody></table>
      </div>"""

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
    links_content = links_html if links else f"""
    <div class="empty">
      <div class="empty-visual">🔗</div>
      <h3>Нет публичных ссылок</h3>
      <p>Создайте ссылку на файл через бота:<br><b>Файл → Поделиться</b></p>
      <a class="btn btn-ghost" href="{bot_url}">Перейти в бота</a>
    </div>"""

    cat_rows = "".join(
        f'<div class="cat-row"><span>{storage.file_icon(k)} {k}</span><span>{v}</span></div>'
        for k, v in stats["by_category"].items()
    ) or '<p class="muted">Нет данных</p>'

    body = f"""
    <header class="header-card">
      <div class="header-top">
        <div class="header-logo">☁️</div>
        <div class="header-title">
          <h1>Облачный</h1>
          <div class="header-sub">{stats['files_count']} файлов · {stats['links_count']} ссылок</div>
        </div>
        <a class="btn btn-ghost btn-sm" href="{bot_url}" title="Telegram">📱</a>
      </div>
      <div class="storage-block">
        <div class="storage-row">
          <span class="storage-label">Хранилище</span>
          <span class="storage-value">{stats['used_fmt']} / {stats['limit_fmt']}</span>
        </div>
        <div class="{bar_cls}"><span style="width:{max(stats['percent'], 2 if stats['used'] else 0)}%"></span></div>
      </div>
    </header>

    <nav class="sidebar-nav">
      <button class="nav-item active" data-tab="files">📁 Файлы</button>
      <button class="nav-item" data-tab="links">🔗 Ссылки</button>
      <button class="nav-item" data-tab="stats">📊 Статистика</button>
      <button class="nav-item" data-tab="help">📖 Справка</button>
    </nav>

    <div class="tab-panel active" data-tab="files">
      <div class="files-toolbar">
        <input class="search" id="search" type="search" placeholder="Поиск файлов..." autocomplete="off">
        <div class="toolbar-actions">
          <select class="sort" id="sort">
            <option value="date-desc">Новые первые</option>
            <option value="name">По имени</option>
            <option value="size">По размеру</option>
          </select>
          <div class="view-toggle">
            <button class="view-btn active" data-view="grid" title="Сетка">▦</button>
            <button class="view-btn" data-view="list" title="Список">☰</button>
          </div>
          <a class="btn btn-primary btn-sm" href="/download-all?token={token}">📦 ZIP</a>
        </div>
      </div>
      <div class="chips">
        <span class="chip active" data-cat="all">Все</span>
        <span class="chip" data-cat="image">🖼 Фото</span>
        <span class="chip" data-cat="doc">📄 Док</span>
        <span class="chip" data-cat="video">🎬 Видео</span>
        <span class="chip" data-cat="audio">🎵 Аудио</span>
        <span class="chip" data-cat="archive">📦 Архив</span>
        <span class="chip" data-cat="code">💻 Код</span>
      </div>
      <div id="file-grid" class="file-grid">{files_content}</div>
      {table_section}
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
    response.set_cookie("cloud_token", token, max_age=315360000, httponly=True, samesite="Lax")
    return response


async def download_handler(request: web.Request) -> web.Response:
    _, session = _require_session(request)
    if not session:
        raise web.HTTPUnauthorized(text="Недействительная ссылка. Получите новую в боте: ⚙️ Настройки → 🌐 Веб-панель.")

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
        raise web.HTTPUnauthorized(text="Недействительная ссылка.")

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
        raise web.HTTPUnauthorized(text="Недействительная ссылка.")

    zip_path = storage.create_user_zip(session["user_id"])
    if not zip_path:
        raise web.HTTPNotFound(text="Нет файлов для архивации")

    return web.FileResponse(zip_path, headers={"Content-Disposition": 'attachment; filename="cloud_files.zip"'})


async def delete_handler(request: web.Request) -> web.Response:
    token, session = _require_session_post(request)
    if not session:
        raise web.HTTPUnauthorized(text="Недействительная ссылка.")

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
        raise web.HTTPUnauthorized(text="Недействительная ссылка.")

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
        raise web.HTTPUnauthorized(text="Недействительная ссылка.")

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
