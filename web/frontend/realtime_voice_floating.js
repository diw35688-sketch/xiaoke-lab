// 实验进行中页面右侧的实时语音浮动面板。
// 只在 run 视图显示；打开后复用 QwenAudio 实时语音组件。
(function () {
  'use strict';

  var mounted = false;
  var unmount = null;
  var panel = null;
  var lastRunState = null;

  function addCss() {
    if (document.getElementById('realtime-voice-float-css')) return;
    var css = [
      '#rvf-toggle{position:fixed;right:18px;bottom:90px;z-index:600;width:44px;height:44px;border-radius:50%;border:1px solid rgba(0,0,0,.10);background:#fff;color:#2563eb;font-size:18px;cursor:pointer;box-shadow:0 6px 20px rgba(15,23,42,.12);display:none;align-items:center;justify-content:center}',
      '#rvf-toggle.on{background:#2563eb;border-color:#2563eb;color:#fff;box-shadow:0 0 0 4px rgba(37,99,235,.18)}',
      '#rvf-panel{position:fixed;right:18px;bottom:90px;z-index:600;width:min(380px,calc(100vw - 28px));height:min(560px,calc(100vh - 120px));background:#fff;border:1px solid #e2e8f0;border-radius:18px;box-shadow:0 18px 50px rgba(15,23,42,.22);display:none;flex-direction:column;overflow:hidden}',
      '#rvf-panel.open{display:flex}',
      '#rvf-head{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid #eef2f7}',
      '#rvf-head strong{font-size:14px;color:#0f172a}',
      '#rvf-head .rvf-status{margin-left:auto;font-size:12px;color:#64748b}',
      '#rvf-close{padding:5px 10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#334155;font-size:12px;cursor:pointer}',
      '#rvf-body{flex:1;min-height:0}',
      '.qwen-rw{display:flex;flex-direction:column;height:100%;background:#fff;overflow:hidden}',
      '.qwen-rw-top{display:flex;align-items:center;gap:8px;padding:10px;border-bottom:1px solid #eef2f7;flex-wrap:wrap}',
      '.qwen-rw-status{margin-left:auto;font-size:12px;color:#64748b}',
      '.qwen-rw-body{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column}',
      '.qwen-rw-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;text-align:center;color:#64748b;padding:24px;font-size:14px}',
      '.qwen-rw-empty p{margin:6px 0 0}',
      '.qwen-rw-sub{font-size:12px;color:#94a3b8}',
      '.qwen-rw-messages{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}',
      '.qwen-rw-msg{display:flex}',
      '.qwen-rw-msg.assistant{justify-content:flex-start}',
      '.qwen-rw-msg.user{justify-content:flex-end}',
      '.qwen-rw-bubble{max-width:82%;padding:9px 12px;border-radius:12px;background:#f1f5f9;color:#0f172a;font-size:14px;line-height:1.6;white-space:pre-wrap}',
      '.qwen-rw-msg.user .qwen-rw-bubble{background:#2563eb;color:#fff}',
      '.qwen-rw-msg.system .qwen-rw-bubble{background:#fffbeb;color:#92400e;font-size:12px;border:1px solid #fde68a}',
      '.qwen-rw-error{margin:8px 14px 14px;padding:8px 12px;border-radius:10px;background:#fef2f2;color:#b91c1c;font-size:13px}',
      '.qwen-rw-info{margin:8px 14px 14px;padding:8px 12px;border-radius:10px;background:#fffbeb;color:#92400e;font-size:13px}',
      '.qwen-rw-active{animation:qwenPulse 1.4s ease-in-out infinite}',
      '@keyframes qwenPulse{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}50%{box-shadow:0 0 0 6px rgba(37,99,235,0)}}',
    ].join('\n');
    var style = document.createElement('style');
    style.id = 'realtime-voice-float-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function closePanel() {
    if (unmount) { unmount(); unmount = null; }
    mounted = false;
    if (panel) panel.classList.remove('open');
    var toggle = document.getElementById('rvf-toggle');
    if (toggle) toggle.classList.remove('on');
  }

  function mountPanel() {
    if (!panel) return;
    panel.classList.add('open');
    var toggle = document.getElementById('rvf-toggle');
    if (toggle) toggle.classList.add('on');
    if (mounted) return;
    mounted = true;
    var body = document.getElementById('rvf-body');
    body.innerHTML = '';
    if (window.QwenRealtimeWidget && window.QwenRealtimeWidget.mountQwenRealtime) {
      unmount = window.QwenRealtimeWidget.mountQwenRealtime(body);
    } else {
      body.innerHTML = '<div style="padding:24px;color:#b91c1c;text-align:center">实时语音组件未加载</div>';
    }
  }

  function syncView() {
    var runState = Boolean(window.shellCurrentView && window.shellCurrentView() === 'run');
    if (runState === lastRunState) return;
    lastRunState = runState;
    var toggle = document.getElementById('rvf-toggle');
    if (!toggle) return;
    toggle.style.display = runState ? 'flex' : 'none';
    if (!runState) closePanel();
    else if (!panel.classList.contains('open')) mountPanel();
  }

  document.addEventListener('DOMContentLoaded', function () {
    addCss();
    var toggle = document.createElement('button');
    toggle.id = 'rvf-toggle';
    toggle.title = '实时语音（实验进行中）';
    toggle.textContent = '🎙';
    document.body.appendChild(toggle);

    panel = document.createElement('div');
    panel.id = 'rvf-panel';
    panel.innerHTML = [
      '<div id="rvf-head">',
      '  <strong>实验实时语音</strong>',
      '  <span class="rvf-status">Qwen Audio</span>',
      '  <button id="rvf-close" type="button">收起</button>',
      '</div>',
      '<div id="rvf-body"></div>',
    ].join('');
    document.body.appendChild(panel);

    toggle.onclick = function () {
      if (panel.classList.contains('open')) closePanel();
      else mountPanel();
    };
    document.getElementById('rvf-close').onclick = closePanel;
    syncView();
    setInterval(syncView, 800);
  });
})();
