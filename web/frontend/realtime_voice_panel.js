// 实时语音功能：在实验助手里直接挂载 QwenAudio 实时语音 React 组件。
// 不跳外部页面、不用 iframe，作为本应用内的一个功能展示在主工作区。
(function () {
  function addCss() {
    var css = [
      '.qwen-rw{height:100%;display:flex;flex-direction:column;min-height:420px;background:#fff}',
      '.qwen-rw-top{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid var(--bd-2);flex-wrap:wrap}',
      '.qwen-rw-status{margin-left:auto;font-size:12px;color:var(--brand-strong);background:var(--brand-50);padding:4px 10px;border-radius:999px}',
      '.qwen-rw-body{flex:1;overflow:auto;padding:14px;min-height:0}',
      '.qwen-rw-empty{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#64748b;text-align:center;gap:6px}',
      '.qwen-rw-empty>div{font-size:42px}',
      '.qwen-rw-empty p{margin:0;font-size:14px}',
      '.qwen-rw-empty .qwen-rw-sub{font-size:12px;color:#94a3b8}',
      '.qwen-rw-messages{display:flex;flex-direction:column;gap:10px}',
      '.qwen-rw-msg{display:flex}',
      '.qwen-rw-msg.user{justify-content:flex-end}',
      '.qwen-rw-msg.assistant{justify-content:flex-start}',
      '.qwen-rw-bubble{max-width:78%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.6;background:var(--n-75);color:var(--n-900);white-space:pre-wrap;word-break:break-word}',
      '.qwen-rw-msg.user .qwen-rw-bubble{background:var(--brand);color:#fff}',
      '.qwen-rw-msg.system .qwen-rw-bubble{background:#fffbeb;color:#92400e;font-size:12px;border:1px solid #fde68a}',
      '.qwen-rw-active{animation:qwenPulse 1.4s ease-in-out infinite}',
      '@keyframes qwenPulse{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.35)}50%{box-shadow:0 0 0 6px rgba(37,99,235,0)}}',
      '.qwen-rw-interrupted{font-size:11px;color:#b45309;margin-left:6px}',
      '.qwen-rw-error{margin:8px 14px 14px;padding:8px 12px;border-radius:10px;background:#fef2f2;color:#b91c1c;font-size:13px}',
      '.qwen-rw-info{margin:8px 14px 14px;padding:8px 12px;border-radius:10px;background:#fffbeb;color:#92400e;font-size:13px}'
    ].join('\n');
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  function register() {
    if (!window.shellRegisterView) return;
    addCss();
    window.shellRegisterView('qwen_audio', function (canvas) {
      canvas.innerHTML = [
        '<div class="qa-wrap" style="height:100%;min-height:480px;display:flex;flex-direction:column;gap:10px">',
        '  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">',
        '    <strong style="font-size:15px">Qwen Audio 实时语音</strong>',
        '    <span id="qa-status" style="font-size:12px;color:#64748b">检测服务状态…</span>',
        '    <button id="qa-start" class="sh-btn" type="button" style="margin-left:auto">启动实时语音</button>',
        '    <button id="qa-exit" class="sh-btn" type="button">关闭并退出</button>',
        '  </div>',
        '  <div id="qa-body" style="flex:1;min-height:420px;border:1px solid var(--bd-2);border-radius:14px;overflow:hidden;background:#fff;position:relative"></div>',
        '</div>'
      ].join('');
      var status = document.getElementById('qa-status');
      var startBtn = document.getElementById('qa-start');
      var body = document.getElementById('qa-body');
      var unmount = null;

      function mountWidget() {
        if (unmount) {
          unmount();
          unmount = null;
        }
        if (window.QwenRealtimeWidget && window.QwenRealtimeWidget.mountQwenRealtime) {
          unmount = window.QwenRealtimeWidget.mountQwenRealtime(body);
        } else {
          body.innerHTML = '<div style="padding:24px;color:#dc2626">实时语音组件尚未加载</div>';
        }
      }

      function showStartHint() {
        if (unmount) { unmount(); unmount = null; }
        body.innerHTML = [
          '<div style="height:100%;display:flex;align-items:center;justify-content:center;text-align:center;color:#64748b;padding:30px;box-sizing:border-box">',
          '  <div><div style="font-size:40px;margin-bottom:12px">🎙️</div>',
          '    <div style="font-weight:600;color:#1b1b1c;margin-bottom:6px">实时语音还没启动</div>',
          '    <div style="font-size:13px">请先在设置里填写 DashScope API Key，然后点击右上角“启动实时语音”。</div></div>',
          '</div>'
        ].join('');
      }

      function currentLabSessionId() {
        try {
          var map = JSON.parse(localStorage.getItem('lab-agent-lab-sessions') || '{}');
          var snapshot = null;
          try { snapshot = window.interactionModeState && window.interactionModeState.current(); } catch (_) {}
          if (snapshot && snapshot.experiment_context === 'protocol') {
            return map['protocol:' + (snapshot.protocol_id || '')] || '';
          }
          return map[snapshot && snapshot.experiment_context || ''] || '';
        } catch (_) {
          return '';
        }
      }

      function syncCurrentConversation() {
        var conversationId = '';
        try { conversationId = localStorage.getItem('lab-agent-conversation-id') || ''; } catch (_) {}
        if (!conversationId) return;
        var labSessionId = currentLabSessionId();
        return fetch('/internal/qwen-conversation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            conversation_id: conversationId,
            lab_session_id: labSessionId || undefined,
          }),
          cache: 'no-store',
        }).catch(function () {});
      }

      function refresh() {
        fetch('/settings/qwen-audio', { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.ok) {
              status.textContent = '运行中：' + d.url;
              status.style.color = '#047857';
              startBtn.textContent = '重新启动';
              syncCurrentConversation();
              mountWidget();
            } else {
              status.textContent = d.dashscope_key_set ? '服务未运行' : '未配置 DashScope Key';
              status.style.color = '#b45309';
              startBtn.textContent = '启动实时语音';
              showStartHint();
            }
          })
          .catch(function () {
            status.textContent = '状态查询失败';
            status.style.color = '#dc2626';
            showStartHint();
          });
      }

      startBtn.onclick = function () {
        startBtn.disabled = true;
        startBtn.textContent = '启动中…';
        fetch('/settings/qwen-audio/start', { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            startBtn.disabled = false;
            status.textContent = d.message || (d.ok ? '已启动' : '启动失败');
            status.style.color = d.ok ? '#047857' : '#dc2626';
            if (d.ok) { syncCurrentConversation(); mountWidget(); }
            else showStartHint();
          })
          .catch(function () {
            startBtn.disabled = false;
            status.textContent = '启动请求失败';
            status.style.color = '#dc2626';
          });
      };

      var exitBtn = document.getElementById('qa-exit');
      if (exitBtn) {
        exitBtn.onclick = function () {
          if (unmount) { unmount(); unmount = null; }
          if (window.shellShow) window.shellShow('run');
        };
      }

      refresh();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', register);
  } else {
    register();
  }
})();
