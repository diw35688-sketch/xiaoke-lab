import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

import network_mode
import phone_access
from asr_application_service import get_asr_application_service

from api.asr import router as asr_router
from api.agent import router as agent_router
from api.automations import router as automations_router
from api.auth import router as auth_router, current_user, create_phone_login_token
from api.calculator import router as calculator_router
from api.chat import router as chat_router
from api.checklists import router as checklists_router
from api.planning import router as planning_router
from api.experiments import router as experiments_router
from api.memories import router as memories_router
from api.network import router as network_router
from api.files import router as files_router
from api.knowledge_base import router as kb_router
from api.logs import router as logs_router
from api.telemetry import router as telemetry_router
from api.notifications import router as notifications_router
from api.papers import router as papers_router
from api.prep_bench import router as prep_bench_router
from api.protocols import router as protocols_router
from api.reagent_prep import router as reagent_prep_router
from api.record import router as record_router
from api.settings import router as settings_router
from api.internal import router as internal_router
from api.storage import router as storage_router
from api.community import router as community_router
from api.community_proxy import router as community_proxy_router
from api.tasks import router as tasks_router
from api.templates import router as templates_router
from api.timers import router as timers_router
from api.tts import router as tts_router
from api.turn import router as turn_router, turn_application_service, turn_store
from api.voice_runtime import router as voice_runtime_router
from config import BASE_DIR
from database.db import initialize_database
from scheduler import start_daily_scheduler
from tasks.task_manager import task_manager

app = FastAPI(title="实验助手 API", version="1.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static")

# 实时语音 WebSocket 反向代理：
# 手机通过公网隧道只能访问 8000 端口，无法直连 QwenAudio 的 3101。
# 浏览器先连本服务 /api/realtime，由这里转发到 127.0.0.1:3101/api/realtime。
# 转发时不带浏览器 Origin，QwenAudio 视作本机回环连接，可绕开公网 Origin 校验。
import asyncio
import websockets

GATEWAY_WS_BASE = "ws://127.0.0.1:3101"

@app.websocket("/api/realtime")
async def realtime_gateway_proxy(websocket: WebSocket):
    # 只允许已登录用户使用实时语音，避免公网隧道被陌生人占用语音通道。
    try:
        from database import user_store
        session_token = websocket.cookies.get("lab_session")
        user = user_store.resolve_session(session_token) if session_token else None
        if user is None:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    target = GATEWAY_WS_BASE + websocket.url.path
    if websocket.url.query:
        target += "?" + websocket.url.query
    try:
        upstream = await websockets.connect(target)
    except Exception:
        await websocket.close(code=1013)
        return
    try:
        async def client_to_upstream():
            try:
                while True:
                    message = await websocket.receive()
                    kind = message.get("type")
                    if kind == "websocket.disconnect":
                        break
                    if "text" in message and message["text"] is not None:
                        await upstream.send(message["text"])
                    elif "bytes" in message and message["bytes"] is not None:
                        await upstream.send(message["bytes"])
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                try:
                    await upstream.close()
                except Exception:
                    pass

        async def upstream_to_client():
            try:
                async for message in upstream:
                    if isinstance(message, str):
                        await websocket.send_text(message)
                    else:
                        await websocket.send_bytes(message)
            except Exception:
                pass
            finally:
                try:
                    await websocket.close()
                except Exception:
                    pass

        await asyncio.gather(client_to_upstream(), upstream_to_client())
    finally:
        try:
            await upstream.close()
        except Exception:
            pass

# HTTP 压缩：文本类响应（HTML/JS/CSS/JSON）压缩后再传输，手机公网隧道下体积约降七成。
# 当前 Starlette 版本不支持 exclude_content_types，音频流直接走默认不压缩的 text/event-stream；
# 若以后升级 Starlette，可再恢复显式排除 application/octet-stream。
app.add_middleware(GZipMiddleware, minimum_size=1000)


# 无需登录即可访问的路径前缀。
# /auth 与 /login 必须放行，否则首次使用时无法创建第一个账号——把自己锁在门外。
# /static 放行是因为登录页本身要加载样式；这些文件不含用户数据。
_PUBLIC_PREFIXES = ("/auth", "/login", "/static", "/health", "/internal", "/favicon.ico")


def _is_public(path: str) -> bool:
    return any(path == item or path.startswith(item + "/") or path.startswith(item)
               for item in _PUBLIC_PREFIXES)


@app.middleware("http")
async def no_cache_for_frontend(request: Request, call_next):
    """微信/手机内置浏览器容易缓存旧静态资源，这里对页面和静态文件强制不缓存。"""
    response = await call_next(request)
    if (
        request.url.path.startswith("/static")
        or request.url.path in ("/", "/phone", "/login")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def require_login(request: Request, call_next):
    """全局登录闸门：未登录只能看到登录页。

    页面导航重定向到 /login，接口调用返回 401 JSON——
    让前端能区分"该跳转"和"该提示重新登录"。
    """
    path = request.url.path
    if request.method == "OPTIONS" or _is_public(path):
        return await call_next(request)
    token = request.cookies.get("lab_session")
    user = current_user(token)
    if user is None:
        accepts_html = "text/html" in (request.headers.get("accept") or "")
        if accepts_html:
            return RedirectResponse("/login", status_code=302)
        return JSONResponse({"detail": "请先登录。"}, status_code=401)
    # 交给下游用，省掉各处重复解析 Cookie
    request.state.user = user
    return await call_next(request)


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
    # 恢复上次网络模式（公网隧道开/关），并清理历史遗留的 cloudflared 进程。
    network_mode.restore_tunnel_mode()




# 静态资源统一版本戳：改前端后把这个常量往后推一位，用户即可拿到新版。
# 历史教训（2026-08-30）：theme.css 加了整块皮肤样式却漏改手写的 ?v=，
# 浏览器按戳吃缓存 → 发的是旧样式表 → 新皮肤整轮"没生效"，且现象极具误导性
# （脚本是新的、样式是旧的）。故不再逐个手敲，改为渲染时统一打戳。
BUILD_VERSION = "20260906-fix-composer"

_STATIC_ASSET_RE = re.compile(r'(/static/[A-Za-z0-9_\-./]+\.(?:js|css))(\?v=[^"\']*)?')


def _stamp_assets(html: str) -> str:
    """给页面里所有 /static 的 js/css 打上统一版本戳（覆盖已有的手写戳）。"""
    return _STATIC_ASSET_RE.sub(lambda m: f"{m.group(1)}?v={BUILD_VERSION}", html)


def _is_mobile(user_agent: str) -> bool:
    """粗略判断是否为手机/平板浏览器：根路径自动进手机专用页。"""
    ua = (user_agent or "").lower()
    markers = ("mobile", "android", "iphone", "ipad", "windows phone")
    return any(marker in ua for marker in markers)


@app.get("/", include_in_schema=False)
def home(request: Request):
    # 手机/公网隧道直接使用电脑端同一界面；通过移动端外壳 CSS/JS 做响应式适配。
    # 电脑界面的手机版 = 默认聊天，点导航可进入实验/工作台。
    page = (BASE_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
    # defer：不阻塞 HTML 解析，且按声明顺序执行（脚本间的隐式依赖顺序不变）。
    page = page.replace(
        '<script src="/static/inworld_tts.js"></script>',
        '<script defer src="/static/local_tts.js?v=20260826-shared-warmup"></script>',
    )
    page = page.replace('</head>', '<link rel="stylesheet" href="/static/theme.css?v=20260905-tool-overflow"></head>')
    page = page.replace('</head>', '<link rel="stylesheet" href="/static/mobile-shell.css?v=20260902-history"></head>')
    scripts = (
        '<script defer src="/static/debug_log.js?v=20260901"></script>'
        '<script defer src="/static/experiment_confirmation.js"></script>'
        '<script defer src="/static/experiment_status.js"></script>'
        '<script defer src="/static/history_panel.js"></script>'
        '<script defer src="/static/memory_panel.js"></script>'
        '<script defer src="/static/conversation.js"></script>'
        '<script defer src="/static/avatar.js"></script>'
        '<script defer src="/static/agent_presence.js?v=20260829-presence"></script>'
        '<script defer src="/static/voice_delivery_client.js?v=20260906-echo-guard"></script>'
        '<script defer src="/static/conversation_turn_store.js?v=20260826-committed-turn"></script>'
        '<script defer src="/static/conversation_block_view.js?v=20260827-clarification-card"></script>'
        '<script defer src="/static/turn_reply_surface.js?v=20260827-progress-cleanup"></script>'
        '<script defer src="/static/conversation_context_blocks.js?v=20260825"></script>'
        '<script defer src="/static/interaction_mode_state.js?v=20260829-storage"></script>'
        '<script defer src="/static/voice_asr.js?v=20260905-unified-mode"></script>'
        '<script defer src="/static/turn_client.js?v=20260827-timing"></script>'
        '<script defer src="/static/streaming_chat_v2.js?v=20260905-unified-mode"></script>'
        '<script defer src="/static/template_planner.js"></script>'
        '<script defer src="/static/task_panel.js"></script>'
        '<script defer src="/static/shell.js?v=20260902-history3"></script>'
        '<script defer src="/static/qwen_realtime_widget.js?v=20260903-qwen-b"></script>'
        '<script defer src="/static/realtime_voice_panel.js?v=20260903-qwen-b"></script>'
        '<script defer src="/static/realtime_voice_inline.js?v=20260906-echo-guard"></script>'
        '<script defer src="/static/mobile_shell.js?v=20260902-history3"></script>'
        '<script defer src="/static/conversation_list.js?v=20260902-history3"></script>'
        '<script defer src="/static/run_canvas.js"></script>'
        '<script defer src="/static/artifact_view.js?v=20260903-artifact"></script>'
        '<script defer src="/static/step_cards.js?v=20260902-shell-fix"></script>'
        '<script defer src="/static/record_ledger_view.js?v=20260827-deviation-values"></script>'
        '<script defer src="/static/record_events.js?v=20260905-sse"></script>'
        '<script defer src="/static/settings.js?v=20260901-hidden"></script>'
        '<script defer src="/static/autofill_guard.js?v=20260903-autofill"></script>'
        '<script defer src="/static/tts_settings.js?v=20260901-volcano-fields"></script>'
        '<script defer src="/static/speak.js?v=20260820"></script>'
        '<script defer src="/static/views.js?v=20260902-library"></script>'
        '<script defer src="/static/agent_panel.js?v=20260903-agent-panel"></script>'
        '<script defer src="/static/personal.js?v=20260903-personal"></script>'
        '<script defer src="/static/protocol_editor.js"></script>'
        '<script defer src="/static/reagent_prep.js?v=20260902-flow"></script>'
        '<script defer src="/static/storage.js?v=20260821"></script>'
        '<script defer src="/static/community.js?v=20260901-telemetry"></script>'
        '<script defer src="/static/kb.js?v=20260905-kb-v2"></script>'
        '<script defer src="/static/notifications.js?v=20260821"></script>'
        '<script defer src="/static/timer_popups.js?v=20260903-timer-popup"></script>'
        '<script defer src="/static/composer.js?v=20260902-svg-icons"></script>'
        '<script defer src="/static/voice_startup_ui.js?v=20260826"></script>'
        '<script defer src="/static/call_silero_vad.js?v=20260826-visible-progress"></script>'
        '<script defer src="/static/wake_word.js?v=20260903-homophone"></script>'
        '<script defer src="/static/phone_call.js?v=20260906-echo-guard"></script>'
    )
    return HTMLResponse(
        _stamp_assets(page.replace("</body>", scripts + "</body>")),
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/m", include_in_schema=False)
def mobile_page():
    """手机专用演示页：大录音按钮 + 转写/追问展示，独立于桌面版布局。"""
    page = (BASE_DIR / "frontend" / "mobile.html").read_text(encoding="utf-8")
    return HTMLResponse(page)


@app.get("/login", include_in_schema=False)
def login_page():
    """登录页；无账号时自动切换为"创建管理员"引导。"""
    page = (BASE_DIR / "frontend" / "login.html").read_text(encoding="utf-8")
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"status": "ok"}
@app.get("/phone/qr")
def phone_qr_data(request: Request):
    """给桌面端弹窗用的公网二维码数据；不在公网时只返回原因，不给局域网地址。"""
    status = network_mode.status()
    if status.get("mode") != "tunnel" or not status.get("public_url"):
        return JSONResponse({"ok": False, "reason": "公网隧道未开启"})
    base_url = str(status["public_url"]).rstrip("/") + "/"
    user = getattr(request.state, "user", None)
    if not user:
        # 桌面端未登录时也自动用本机第一个账号，保证扫码永远不需要登录。
        from database import user_store
        users = user_store.list_users()
        user = users[0] if users else None
    if not user:
        return JSONResponse({"ok": False, "reason": "本机还没有账号，请先初始化系统。", "status_code": 400})
    token = create_phone_login_token(user)
    qr_url = base_url + "auth/phone-login/" + token
    return JSONResponse({
        "ok": True,
        "url": qr_url,
        "display_url": base_url,
        "qr_svg": phone_access.qr_svg(qr_url),
        "mode": status.get("mode"),
        "token_ttl_seconds": 365 * 24 * 60 * 60,
    })


@app.get("/phone", include_in_schema=False)
def phone_access_page(request: Request):
    """手机访问入口页：桌面端打开本页，手机扫二维码即可访问。"""
    status = network_mode.status()
    url = status.get("public_url") or status.get("lan_url") or phone_access.phone_url(request)
    # 二维码指向电脑界面的手机版（聊天默认，实验开始后进入工作台卡片）
    base_url = url.rstrip("/") + "/"
    user = getattr(request.state, "user", None)
    if user:
        # 电脑已登录：生成一次性扫码令牌，手机扫码后自动登录，不再要求手机输入账号。
        token = create_phone_login_token(user)
        qr_url = base_url + "auth/phone-login/" + token
    else:
        qr_url = base_url + "login"
    svg = phone_access.qr_svg(qr_url)
    qr_block = svg if svg else f"<pre>{qr_url}</pre>"
    mode_label = "公网隧道" if status.get("mode") == "tunnel" else "局域网"
    label_note = "扫码后自动登录，无需在手机上输账号密码。" if user else "扫码后需要登录。"
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
<div class="qr">{qr_block}</div><div class="url">{base_url}</div><p class="note">{label_note} 手机浏览器需要允许麦克风权限；局域网地址是 HTTP，公网隧道是 HTTPS。</p>
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
  </body></html>""".replace("{qr_block}", qr_block).replace("{base_url}", base_url).replace("{mode_box}", mode_box_html)
    return HTMLResponse(html)


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(checklists_router)
app.include_router(planning_router)
app.include_router(calculator_router)
app.include_router(experiments_router)
app.include_router(memories_router)
app.include_router(network_router)
app.include_router(files_router)
app.include_router(kb_router)
app.include_router(logs_router)
app.include_router(telemetry_router)
app.include_router(notifications_router)
app.include_router(papers_router)
app.include_router(prep_bench_router)
app.include_router(timers_router)
app.include_router(templates_router)
app.include_router(tasks_router)
app.include_router(settings_router)
app.include_router(internal_router)
app.include_router(protocols_router)
app.include_router(reagent_prep_router)
app.include_router(storage_router)
app.include_router(community_router)
app.include_router(community_proxy_router)
app.include_router(asr_router)
app.include_router(agent_router)
app.include_router(automations_router)
app.include_router(record_router)
app.include_router(tts_router)
app.include_router(voice_runtime_router)
app.include_router(turn_router)
