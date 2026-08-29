import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import network_mode
import phone_access
from asr_application_service import get_asr_application_service

from api.asr import router as asr_router
from api.calculator import router as calculator_router
from api.chat import router as chat_router
from api.experiments import router as experiments_router
from api.memories import router as memories_router
from api.network import router as network_router
from api.files import router as files_router
from api.logs import router as logs_router
from api.telemetry import router as telemetry_router
from api.notifications import router as notifications_router
from api.protocols import router as protocols_router
from api.reagent_prep import router as reagent_prep_router
from api.record import router as record_router
from api.settings import router as settings_router
from api.storage import router as storage_router
from api.community import router as community_router
from api.community_proxy import router as community_proxy_router
from api.tasks import router as tasks_router
from api.templates import router as templates_router
from api.tts import router as tts_router
from api.turn import router as turn_router, turn_application_service, turn_store
from api.voice_runtime import router as voice_runtime_router
from config import BASE_DIR
from database.db import initialize_database
from scheduler import start_daily_scheduler
from tasks.task_manager import task_manager

app = FastAPI(title="实验助手 API", version="1.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static")


@app.middleware("http")
async def request_debug_log(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        print(
            f"[REQ] {time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"{request.method} {request.url.path} status=500 duration=?"
            f" error={type(exc).__name__} {exc}",
            flush=True,
        )
        raise
    duration = (time.perf_counter() - start) * 1000
    print(
        f"[REQ] {time.strftime('%Y-%m-%d %H:%M:%S')} "
        f"{request.method} {request.url.path} status={response.status_code} "
        f"duration={duration:.0f}ms",
        flush=True,
    )
    return response


@app.on_event("startup")
def startup():
    initialize_database()
    turn_application_service.recover_after_restart()
    get_asr_application_service().cleanup_pending(
        referenced_paths=turn_store.referenced_audio_paths()
    )
    start_daily_scheduler()
    task_manager.start()




def _is_mobile(user_agent: str) -> bool:
    """粗略判断是否为手机/平板浏览器：根路径自动进手机专用页。"""
    ua = (user_agent or "").lower()
    markers = ("mobile", "android", "iphone", "ipad", "windows phone")
    return any(marker in ua for marker in markers)


@app.get("/", include_in_schema=False)
def home(request: Request):
    if _is_mobile(request.headers.get("user-agent", "")):
        return HTMLResponse((BASE_DIR / "frontend" / "mobile.html").read_text(encoding="utf-8"))
    # 公网隧道默认打开移动端流程卡片，方便手机/外部访问
    try:
        if network_mode.status().get("mode") == "tunnel":
            return HTMLResponse((BASE_DIR / "frontend" / "mobile.html").read_text(encoding="utf-8"))
    except Exception:
        pass
    page = (BASE_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
    page = page.replace('/static/inworld_tts.js', '/static/local_tts.js?v=20260826-shared-warmup')
    page = page.replace('</head>', '<link rel="stylesheet" href="/static/theme.css"></head>')
    scripts = (
        '<script src="/static/debug_log.js?v=20260901"></script>'
        '<script src="/static/experiment_confirmation.js"></script>'
        '<script src="/static/experiment_status.js"></script>'
        '<script src="/static/history_panel.js"></script>'
        '<script src="/static/memory_panel.js"></script>'
        '<script src="/static/conversation.js"></script>'
        '<script src="/static/avatar.js"></script>'
        '<script src="/static/voice_delivery_client.js?v=20260825-voice-timing"></script>'
        '<script src="/static/conversation_turn_store.js?v=20260826-committed-turn"></script>'
        '<script src="/static/conversation_block_view.js?v=20260827-clarification-card"></script>'
        '<script src="/static/turn_reply_surface.js?v=20260827-progress-cleanup"></script>'
        '<script src="/static/conversation_context_blocks.js?v=20260825"></script>'
        '<script src="/static/interaction_mode_state.js?v=20260829-storage"></script>'
        '<script src="/static/voice_asr.js?v=20260827-clarification-card"></script>'
        '<script src="/static/turn_client.js?v=20260827-timing"></script>'
        '<script src="/static/streaming_chat_v2.js?v=20260829-explicit-modes"></script>'
        '<script src="/static/template_planner.js"></script>'
        '<script src="/static/task_panel.js"></script>'
        '<script src="/static/shell.js?v=20260901-telemetry"></script>'
        '<script src="/static/conversation_list.js?v=20260818"></script>'
        '<script src="/static/run_canvas.js"></script>'
        '<script src="/static/step_cards.js?v=20260827-restore"></script>'
        '<script src="/static/record_ledger_view.js?v=20260827-deviation-values"></script>'
        '<script src="/static/settings.js?v=20260901-hidden"></script>'
        '<script src="/static/tts_settings.js?v=20260901-volcano-fields"></script>'
        '<script src="/static/speak.js?v=20260820"></script>'
        '<script src="/static/views.js?v=20260827-unified-ledger"></script>'
        '<script src="/static/protocol_editor.js"></script>'
        '<script src="/static/reagent_prep.js?v=20260820"></script>'
        '<script src="/static/storage.js?v=20260821"></script>'
        '<script src="/static/community.js?v=20260901-telemetry"></script>'
        '<script src="/static/notifications.js?v=20260821"></script>'
        '<script src="/static/composer.js?v=20260901-telemetry"></script>'
          '<script src="/static/voice_startup_ui.js?v=20260826"></script>'
          '<script src="/static/call_silero_vad.js?v=20260826-visible-progress"></script>'
        '<script src="/static/phone_call.js?v=20260827-clarification-card"></script>'
    )
    return HTMLResponse(
        page.replace("</body>", scripts + "</body>"),
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/m", include_in_schema=False)
def mobile_page():
    """手机专用演示页：大录音按钮 + 转写/追问展示，独立于桌面版布局。"""
    page = (BASE_DIR / "frontend" / "mobile.html").read_text(encoding="utf-8")
    return HTMLResponse(page)


@app.get("/health")
def health():
    return {"status": "ok"}
@app.get("/phone", include_in_schema=False)
def phone_access_page(request: Request):
    """手机访问入口页：桌面端打开本页，手机扫二维码即可访问。"""
    status = network_mode.status()
    url = status.get("public_url") or status.get("lan_url") or phone_access.phone_url(request)
    # 二维码固定指向手机专用页，扫码直接进大按钮版本
    url = url.rstrip("/") + "/m"
    svg = phone_access.qr_svg(url)
    qr_block = svg if svg else f"<pre>{url}</pre>"
    mode_label = "公网隧道" if status.get("mode") == "tunnel" else "局域网"
    error_text = request.query_params.get("error", "")
    error_html = f'<div style="color:#c2410c;font-size:12px;margin-top:8px">{error_text}</div>' if error_text else ''
    mode_box_html = (
        '<div id="mode-box" style="margin-top:16px;font-size:13px;color:#334155">'
        '当前模式：' + mode_label + '<br>'
        '<button onclick="switchMode(\'lan\')" style="display:inline-block;margin:8px 6px 0 0;padding:7px 14px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#334155;text-decoration:none">局域网</button>'
        '<button onclick="switchMode(\'tunnel\')" style="display:inline-block;margin:8px 6px 0 0;padding:7px 14px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#334155;text-decoration:none">公网隧道</button>'
        '<div id="mode-msg" style="margin-top:8px;color:#697586"></div>'
        + error_html
        + '</div>'
    )
    html = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>手机访问实验助手</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f7fb;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#18212f}
  .card{background:#fff;border-radius:18px;box-shadow:0 12px 35px rgba(28,39,65,.08);padding:30px 34px;text-align:center;max-width:520px;width:calc(100vw - 32px)}
  h1{font-size:20px;margin:0 0 8px}.sub{color:#697586;font-size:13px;margin:0 0 20px;line-height:1.7}
  .qr{display:block;margin:0 auto;width:280px;height:280px}pre{font-size:12px;background:#f1f5f9;padding:12px;border-radius:10px;word-break:break-all}
  .url{font-size:15px;font-weight:600;margin:18px 0 6px}.note{color:#697586;font-size:12px;line-height:1.7}
</style></head>
<body><main class="card"><h1>手机访问实验助手</h1><p class="sub">手机和这台电脑连接同一个 WiFi，扫码后即可用手机操作。</p>
<div class="qr">{qr_block}</div><div class="url">{url}</div><p class="note">手机浏览器需要允许麦克风权限。若使用 HTTPS 自签名证书，请在手机上信任该证书。</p>
</main>
  {mode_box}
  <script>
    var _pollTimer=null;
    function switchMode(mode){
      var msg=document.getElementById('mode-msg');
      msg.textContent='正在切换…';
      fetch('/network/mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:mode})})
        .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d}})})
        .then(function(res){
          if(!res.ok){msg.textContent=res.d.detail||'切换失败';return;}
          pollStatus();
        }).catch(function(e){msg.textContent='切换失败：'+e.message});
    }
    function pollStatus(){
      fetch('/network/status').then(function(r){return r.json()}).then(function(s){
        var msg=document.getElementById('mode-msg');
        if(s.state==='running'&&s.public_url){
          msg.textContent='公网隧道已就绪：'+s.public_url;
          setTimeout(function(){location.reload();},800);
          return;
        }
        if(s.state==='lan'&&s.mode==='lan'){
          msg.textContent='已切换到局域网';
          setTimeout(function(){location.reload();},600);
          return;
        }
        if(s.state==='error'){
          msg.textContent=s.error||'隧道启动失败';
          return;
        }
        msg.textContent='公网隧道启动中…';
        clearTimeout(_pollTimer);
        _pollTimer=setTimeout(pollStatus,1200);
      }).catch(function(e){var msg=document.getElementById('mode-msg');msg.textContent='状态查询失败：'+e.message;});
    }
  </script>
  </body></html>""".replace("{qr_block}", qr_block).replace("{url}", url).replace("{mode_box}", mode_box_html)
    return HTMLResponse(html)


app.include_router(chat_router)
app.include_router(calculator_router)
app.include_router(experiments_router)
app.include_router(memories_router)
app.include_router(network_router)
app.include_router(files_router)
app.include_router(logs_router)
app.include_router(telemetry_router)
app.include_router(notifications_router)
app.include_router(templates_router)
app.include_router(tasks_router)
app.include_router(settings_router)
app.include_router(protocols_router)
app.include_router(reagent_prep_router)
app.include_router(storage_router)
app.include_router(community_router)
app.include_router(community_proxy_router)
app.include_router(asr_router)
app.include_router(record_router)
app.include_router(tts_router)
app.include_router(voice_runtime_router)
app.include_router(turn_router)
