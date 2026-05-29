"""Админ-панель: мониторинг системы и алерты в Telegram."""

import html
import json

import config
import monitoring
from aiohttp import web

_ADMIN_CSS = """
:root {
  --bg:#0b0f19; --surface:#141925; --surface2:#1c2333; --border:#2a3347;
  --text:#eef2ff; --muted:#94a3b8; --accent:#3b82f6; --danger:#ef4444;
  --ok:#22c55e; --warn:#eab308; --radius:14px;
}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.app{max-width:1000px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:0 0 4px}
h2{font-size:1rem;margin:0 0 12px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
@media(min-width:640px){.grid{grid-template-columns:repeat(4,1fr)}}
.stat{background:var(--surface2);border-radius:12px;padding:14px;text-align:center}
.stat-val{font-size:1.3rem;font-weight:700}
.stat-label{font-size:.72rem;color:var(--muted);margin-top:4px}
.ok{color:var(--ok)} .bad{color:var(--danger)} .warn{color:var(--warn)}
.bar{height:8px;background:var(--surface2);border-radius:999px;overflow:hidden;margin:8px 0}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#06b6d4)}
.muted{color:var(--muted);font-size:.85rem}
.events{max-height:320px;overflow-y:auto;font-size:.82rem}
.event{padding:8px 0;border-bottom:1px solid var(--border);display:flex;gap:8px}
.event-time{color:var(--muted);white-space:nowrap;min-width:120px}
.event-error{color:#fca5a5}.event-warn{color:#fde047}.event-info{color:var(--text)}
textarea,input[type=text]{width:100%;padding:10px;border-radius:10px;border:1px solid var(--border);
  background:var(--surface2);color:var(--text);font-size:14px;font-family:inherit}
textarea{min-height:80px;resize:vertical}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 16px;border-radius:10px;
  border:none;font-weight:600;cursor:pointer;font-size:.9rem;margin-top:8px;margin-right:8px}
.btn-primary{background:var(--accent);color:#fff}
.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--text)}
.btn-danger{background:rgba(239,68,68,.2);color:#fca5a5;border:1px solid rgba(239,68,68,.3)}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.7rem;font-weight:600}
.badge-ok{background:rgba(34,197,94,.15);color:#86efac}
.badge-bad{background:rgba(239,68,68,.15);color:#fca5a5}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--surface2);
  border:1px solid var(--border);padding:10px 20px;border-radius:999px;display:none;z-index:99}
"""


def _check_admin(request: web.Request) -> bool:
    if not config.ADMIN_SECRET:
        return False
    key = request.query.get("key") or request.cookies.get("admin_key")
    return key == config.ADMIN_SECRET


def _deny() -> web.Response:
    raise web.HTTPNotFound()


def _page(body: str, key: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Админ — Облачный</title>
<style>{_ADMIN_CSS}</style>
</head><body data-key="{html.escape(key)}">
<div id="toast"></div>
<div class="app">{body}</div>
<script>{_ADMIN_JS}</script>
</body></html>"""


_ADMIN_JS = """
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.style.display='block';
  clearTimeout(toast._t);toast._t=setTimeout(()=>t.style.display='none',2500);}
async function api(path,method='GET',body=null){
  const key=document.body.dataset.key;
  const opts={method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify({...body,key});
  const r=await fetch(path+(path.includes('?')?'&':'?')+'key='+encodeURIComponent(key),opts);
  if(!r.ok)throw new Error(await r.text());
  return r.json();
}
async function refresh(){
  const s=await api('/admin/api/stats');
  document.getElementById('stats').innerHTML=renderStats(s);
  document.getElementById('events').innerHTML=renderEvents(s.events);
  document.getElementById('updated').textContent='Обновлено: '+new Date().toLocaleTimeString('ru');
}
function renderStats(s){
  const tg=s.telegram_ok?'<span class="badge badge-ok">OK</span>':'<span class="badge badge-bad">DOWN</span>';
  const dp=s.disk.percent,dm=s.memory.percent;
  const dc=dp>=85?'bad':dp>=70?'warn':'ok';
  const mc=dm>=90?'bad':dm>=75?'warn':'ok';
  return `<div class="grid">
    <div class="stat"><div class="stat-val">${s.uptime}</div><div class="stat-label">Uptime</div></div>
    <div class="stat"><div class="stat-val">${s.users}</div><div class="stat-label">Пользователей</div></div>
    <div class="stat"><div class="stat-val">${s.files}</div><div class="stat-label">Файлов</div></div>
    <div class="stat"><div class="stat-val">${s.links}</div><div class="stat-label">Ссылок</div></div>
  </div>
  <div style="margin-top:14px">
    <div class="row"><span>Telegram</span>${tg} <span class="muted">ошибок: ${s.telegram_errors}</span></div>
    <div class="row"><span>Диск</span><span class="${dc}">${dp}%</span></div>
    <div class="bar"><span style="width:${dp}%"></span></div>
    <div class="row"><span>RAM</span><span class="${mc}">${dm}%</span></div>
    <div class="bar"><span style="width:${dm}%"></span></div>
    <div class="row muted">Load: ${s.load['1m']} / ${s.load['5m']} / ${s.load['15m']}</div>
    <div class="row muted">Хранилище: ${s.storage_used_fmt} · data/: ${s.data_dir_size_fmt}</div>
    <div class="row muted">Сессии веб: ${s.sessions} · Прокси: ${s.proxy?'да':'нет'}</div>
  </div>`;
}
function renderEvents(events){
  if(!events.length)return'<p class="muted">Событий пока нет</p>';
  return events.map(e=>`<div class="event"><span class="event-time">${e.time}</span>
    <span class="event-${e.level}">${e.message}</span></div>`).join('');
}
async function sendMsg(){
  const text=document.getElementById('msg').value.trim();
  if(!text)return toast('Введите текст');
  try{const r=await api('/admin/api/notify','POST',{text});toast('Отправлено: '+r.sent);document.getElementById('msg').value='';}
  catch(e){toast('Ошибка: '+e.message);}
}
async function testAlert(){
  try{await api('/admin/api/test-alert','POST',{});toast('Тестовый алерт отправлен');}
  catch(e){toast('Ошибка: '+e.message);}
}
document.addEventListener('DOMContentLoaded',()=>{
  refresh(); setInterval(refresh,30000);
  document.getElementById('btn-send').onclick=sendMsg;
  document.getElementById('btn-test').onclick=testAlert;
  document.getElementById('btn-refresh').onclick=refresh;
});
"""


async def admin_index(request: web.Request) -> web.Response:
    if not _check_admin(request):
        return _deny()

    key = request.query.get("key", "")
    body = """
    <h1>🛡️ Админ-панель</h1>
    <p class="muted" id="updated">Загрузка...</p>
    <div class="card"><h2>Система</h2><div id="stats">...</div></div>
    <div class="card">
      <h2>📨 Сообщение в Telegram</h2>
      <textarea id="msg" placeholder="Текст для админов в Telegram (HTML)"></textarea>
      <button class="btn btn-primary" id="btn-send">Отправить</button>
      <button class="btn btn-ghost" id="btn-test">🔔 Тест алерта</button>
      <button class="btn btn-ghost" id="btn-refresh">🔄 Обновить</button>
    </div>
    <div class="card"><h2>📋 Журнал событий</h2><div class="events" id="events">...</div></div>
    """
    resp = web.Response(text=_page(body, key), content_type="text/html")
    resp.set_cookie("admin_key", key, max_age=86400 * 7, httponly=True, samesite="Strict")
    return resp


async def admin_stats_api(request: web.Request) -> web.Response:
    if not _check_admin(request):
        return _deny()
    stats = monitoring.get_system_stats()
    stats["events"] = monitoring.get_events(40)
    return web.json_response(stats)


async def admin_notify_api(request: web.Request) -> web.Response:
    if not _check_admin(request):
        return _deny()
    try:
        data = await request.json()
    except Exception:
        data = {}
    if data.get("key") != config.ADMIN_SECRET:
        raise web.HTTPForbidden()
    text = (data.get("text") or "").strip()
    if not text:
        raise web.HTTPBadRequest(text="Пустой текст")
    sent = await monitoring.send_admin_message(text)
    return web.json_response({"ok": True, "sent": sent})


async def admin_test_alert_api(request: web.Request) -> web.Response:
    if not _check_admin(request):
        return _deny()
    try:
        data = await request.json()
    except Exception:
        data = {}
    if data.get("key") != config.ADMIN_SECRET:
        raise web.HTTPForbidden()
    ok = await monitoring.alert("🔔 Тестовый алерт из админ-панели", level="info", key=None)
    return web.json_response({"ok": ok})


def register_admin_routes(app: web.Application) -> None:
    if not config.ADMIN_SECRET:
        return
    app.router.add_get("/admin", admin_index)
    app.router.add_get("/admin/api/stats", admin_stats_api)
    app.router.add_post("/admin/api/notify", admin_notify_api)
    app.router.add_post("/admin/api/test-alert", admin_test_alert_api)
