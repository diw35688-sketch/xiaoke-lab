// 移动端 QwenAudio 实时语音：不跳页面，全屏浮层内挂载同一个实时语音组件。
// 同时提供 reportVoiceTranscript，让实时语音组件的对话能同步到后端会话和实验卡片。
(function () {
  'use strict';

  /* ── 语音转写同步：把 QwenAudio 实时语音的 transcript 写入后端会话 ── */
  function currentLabSessionId() {
    try {
      var map = JSON.parse(localStorage.getItem('lab-agent-lab-sessions') || '{}');
      return map['protocol:'] || map['protocol'] || map[''] || '';
    } catch (_) { return ''; }
  }

  function report(msg) {
    try {
      fetch('/internal/voice-client-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      }).catch(function () {});
    } catch (_) {}
  }

  /**
   * 由 qwen_realtime_widget.js 在 transcript.final 事件时调用。
   * 把语音转写写入后端 → 触发实验卡片刷新 → 自动跳转实验视图。
   */
  window.reportVoiceTranscript = function (role, content, turnId) {
    var conversationId = '';
    try { conversationId = localStorage.getItem('lab-agent-conversation-id') || ''; } catch (_) {}
    report('mobile voiceTranscript role=' + role + ' conv=' + (conversationId || '(empty)') + ' len=' + String(content || '').length);
    if (!conversationId || !content) return;

    var labSessionId = currentLabSessionId();
    if (labSessionId) window.__labSessionId = labSessionId;

    try {
      fetch('/internal/voice-transcript', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          role: role,
          content: content,
          turn_id: turnId || '',
          lab_session_id: labSessionId || undefined,
        }),
      }).then(function (res) {
        report('mobile voiceTranscript response status=' + res.status);
        return res.json();
      }).then(function () {
        // 通知实验卡片刷新
        try { window.dispatchEvent(new CustomEvent('lab:experiment-changed')); } catch (_) {}
        // 助手回复时，如果提到了实验操作，自动跳转到实验视图
        if (role === 'assistant') {
          var text = String(content || '');
          if (text.indexOf('实验方案已加载') >= 0
              || text.indexOf('已切换到') >= 0
              || text.indexOf('实验已启动') >= 0
              || text.indexOf('已成功启动') >= 0
              || text.indexOf('已成功切换') >= 0
              || text.indexOf('已开始') >= 0
              || text.indexOf('已启动') >= 0
              || text.indexOf('已记录') >= 0
              || text.indexOf('已进入') >= 0
              || text.indexOf('下一步') >= 0
              || text.indexOf('当前是') >= 0
              || text.indexOf('当前第') >= 0) {
            // 手机端：自动切到实验卡片视图
            var cardView = document.getElementById('card-view');
            var chatView = document.getElementById('chat-view');
            if (cardView && chatView) {
              chatView.style.display = 'none';
              cardView.style.display = 'block';
            }
          }
        }
        // 刷新实验状态（手机端用 loadReal）
        if (window.MobileCards && typeof window.MobileCards.loadReal === 'function') {
          window.MobileCards.loadReal();
        }
      }).catch(function (e) {
        report('mobile voiceTranscript error=' + String(e));
      });
    } catch (_) {}
  };

  /* ── 浮层挂载 ── */

  function addCss() {
    if (document.getElementById('mobile-realtime-css')) return;
    var css = [
      '#m-qwen-realtime-overlay{position:fixed;inset:0;background:#f6f7fb;z-index:9999;display:none;flex-direction:column}',
      '#m-qwen-realtime-overlay.open{display:flex}',
      '#m-qwen-realtime-overlay .m-rw-head{display:flex;align-items:center;gap:10px;padding:12px 14px;background:#fff;border-bottom:1px solid #e2e8f0}',
      '#m-qwen-realtime-overlay .m-rw-head strong{font-size:15px}',
      '#m-qwen-realtime-overlay .m-rw-close{margin-left:auto;padding:7px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#334155;font-size:13px}',
      '#m-qwen-realtime-body{flex:1;min-height:0;padding:12px;box-sizing:border-box}',
      '.qwen-rw{display:flex;flex-direction:column;height:100%;background:#fff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden}',
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
    style.id = 'mobile-realtime-css';
    style.textContent = css;
    document.head.appendChild(style);
  }

  function el(id) { return document.getElementById(id); }

  function closeOverlay() {
    var overlay = document.getElementById('m-qwen-realtime-overlay');
    if (overlay) overlay.classList.remove('open');
  }

  function openOverlay() {
    addCss();
    // 全局单例防护：卸载其他地方已挂的 widget
    if (window.__qwenRealtimeUnmount) {
      try { window.__qwenRealtimeUnmount(); } catch (e) {}
      window.__qwenRealtimeUnmount = null;
    }
    var existing = document.getElementById('m-qwen-realtime-overlay');
    if (!existing) {
      var overlay = document.createElement('div');
      overlay.id = 'm-qwen-realtime-overlay';
      overlay.innerHTML = [
        '<div class="m-rw-head">',
        '  <strong>实时语音（Qwen Audio）</strong>',
        '  <button id="m-qwen-realtime-close" class="m-rw-close" type="button">关闭</button>',
        '</div>',
        '<div id="m-qwen-realtime-body"></div>',
      ].join('');
      document.body.appendChild(overlay);
      document.getElementById('m-qwen-realtime-close').onclick = closeOverlay;
    }
    var overlay = document.getElementById('m-qwen-realtime-overlay');
    overlay.classList.add('open');
    var body = document.getElementById('m-qwen-realtime-body');
    body.innerHTML = '';
    if (window.QwenRealtimeWidget && window.QwenRealtimeWidget.mountQwenRealtime) {
      var unmountFn = window.QwenRealtimeWidget.mountQwenRealtime(body);
      window.__qwenRealtimeUnmount = function () {
        try { if (unmountFn) unmountFn(); } catch (e) {}
        window.__qwenRealtimeUnmount = null;
      };
    } else {
      body.innerHTML = '<div style="padding:24px;color:#b91c1c;text-align:center">实时语音组件未加载，请刷新重试</div>';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('m-realtime-voice');
    if (!btn) return;
    btn.onclick = openOverlay;
  });
})();
