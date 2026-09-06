// 内嵌式实时语音：不弹任何悬浮框/独立面板。
// 组件挂在一个隐藏容器里，用输入框旁的 ▥▥ 按钮直接开启/关闭。
(function () {
  'use strict';

  var mounted = false;
  var active = false;
  var retryTimer = null;
  var retryCount = 0;
  var refreshTimer = null;

  function scheduleConversationRefresh(conversationId) {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      refreshTimer = null;
      try {
        // 无论当前在哪个视图（聊天页/实验进行中），都要刷新聊天历史，
        // 否则语音交互后右侧聊天框不显示新消息，只能手动刷新才出现。
        if (conversationId && window.switchConversation) {
          window.switchConversation(conversationId);
        }
        if (window.chatHomeReload) {
          window.chatHomeReload();
        }
      } catch (_) {}
    }, 600);
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

  function syncConversationContext() {
    var conversationId = '';
    try { conversationId = localStorage.getItem('lab-agent-conversation-id') || ''; } catch (_) {}
    if (!conversationId) return;
    var labSessionId = currentLabSessionId();
    if (labSessionId) window.__labSessionId = labSessionId;
    try {
      fetch('/internal/qwen-conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          lab_session_id: labSessionId || undefined,
        }),
      }).catch(function () {});
    } catch (_) {}
  }

  function report(message) {
    try {
      fetch('/internal/voice-client-log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message }),
      }).catch(function () {});
    } catch (_) {}
  }

  window.reportVoiceTranscript = function (role, content, turnId) {
    var conversationId = '';
    // TTS 回声保护：助手说话期间及结束后 1.5s 内的用户语音视为回声丢弃
    if (role === 'user') {
      var sinceTTS = Date.now() - (window.__lastTTSFinishedAt || 0);
      if (window.__ttsSpeaking || sinceTTS < 1500) {
        report('echo-suppressed role=user speaking=' + !!window.__ttsSpeaking + ' since=' + sinceTTS + ' text=' + String(content).slice(0, 60));
        return;
      }
    }
    try { conversationId = window.__labConversationId = localStorage.getItem('lab-agent-conversation-id') || ''; } catch (_) {}
    report('voiceTranscript called role=' + role + ' conv=' + (conversationId || '(empty)') + ' len=' + String(content || '').length);
    if (!conversationId || !content) return;
    try {
      fetch('/internal/voice-transcript', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          role: role,
          content: content,
          turn_id: turnId || '',
          lab_session_id: window.__labSessionId || undefined,
        }),
      }).then(function (res) {
        report('voiceTranscript response status=' + res.status);
        return res.json();
      }).then(function () {
        try { window.dispatchEvent(new CustomEvent('lab:experiment-changed')); } catch (_) {}
        // 语音里确认已启动/已切到实验方案时，自动进入“实验进行中”，
        // 避免停留在聊天页。
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
            try { if (window.shellShow) window.shellShow('run'); } catch (_) {}
          }
        }
        scheduleConversationRefresh(conversationId);
      }).catch(function (e) {
        report('voiceTranscript error=' + String(e));
      });
    } catch (_) {}
  };

  function ensureHiddenWidget() {
    if (mounted) return;
    mounted = true;
    if (!document.getElementById('realtime-voice-hidden')) {
      var host = document.createElement('div');
      host.id = 'realtime-voice-hidden';
      host.style.position = 'fixed';
      host.style.left = '-9999px';
      host.style.top = '0';
      host.style.width = '1px';
      host.style.height = '1px';
      host.style.opacity = '0';
      host.style.pointerEvents = 'none';
      host.style.zIndex = '-1';
      document.body.appendChild(host);
    }
    var host = document.getElementById('realtime-voice-hidden');
    host.innerHTML = '';
    if (window.QwenRealtimeWidget && window.QwenRealtimeWidget.mountQwenRealtime) {
      window.QwenRealtimeWidget.mountQwenRealtime(host);
      report('hidden widget mounted, __labRealtimeStart=' + (typeof window.__labRealtimeStart));
    } else {
      report('hidden widget mount: QwenRealtimeWidget missing');
    }
  }

  function syncButton() {
    var btn = document.getElementById('cp-realtime-voice');
    if (btn) btn.classList.toggle('active', active);
    return active;
  }

  function sendCommand(enabled) {
    try {
      window.dispatchEvent(new CustomEvent('lab:realtime-voice-command', {
        detail: { enabled: enabled },
      }));
    } catch (_) {}
  }

  function retryUntilReady() {
    if (active) { retryCount = 0; return; }
    if (retryCount >= 4) { retryCount = 0; report('retry exhausted active=' + active); return; }
    retryCount += 1;
    report('retry #' + retryCount + ' active=' + active + ' hasStart=' + (typeof window.__labRealtimeStart === 'function'));
    if (typeof window.__labRealtimeStart === 'function') window.__labRealtimeStart();
    else sendCommand(true);
    retryTimer = setTimeout(retryUntilReady, 900);
  }

  window.realtimeVoiceToggle = function () {
    ensureHiddenWidget();
    var next = !active;
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    retryCount = 0;
    report('toggle next=' + next + ' activeBefore=' + active
      + ' hasStart=' + (typeof window.__labRealtimeStart === 'function')
      + ' hasStop=' + (typeof window.__labRealtimeStop === 'function'));
    if (next) {
      // 先确保 QwenAudio 后台知道当前浏览器正在看的会话/实验，
      // 避免它调用 MCP 工具写到旧会话。
      syncConversationContext();
      if (typeof window.__labRealtimeStart === 'function') window.__labRealtimeStart();
      else sendCommand(true);
      retryTimer = setTimeout(retryUntilReady, 900);
    } else {
      if (typeof window.__labRealtimeStop === 'function') window.__labRealtimeStop();
      else sendCommand(false);
    }
    syncButton();
  };

  window.addEventListener('lab:realtime-voice-state', function (event) {
    active = Boolean(event.detail && event.detail.enabled);
    window.__realtimeVoiceActive = active;
    syncButton();
    report('state active=' + active);
    if (active && retryTimer) { clearTimeout(retryTimer); retryTimer = null; retryCount = 0; }
  });

  window.addEventListener('lab:realtime-voice-error', function (event) {
    var d = event.detail || {};
    report('voice-error error=' + d.error + ' connectionState=' + d.connectionState + ' inputReady=' + d.inputReady + ' enabled=' + d.enabled);
  });

  document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('realtime-voice-hidden')) {
      var host = document.createElement('div');
      host.id = 'realtime-voice-hidden';
      host.style.position = 'fixed';
      host.style.left = '-9999px';
      host.style.top = '0';
      host.style.width = '1px';
      host.style.height = '1px';
      host.style.opacity = '0';
      host.style.pointerEvents = 'none';
      host.style.zIndex = '-1';
      document.body.appendChild(host);
    }
    // 页面加载时就把组件挂到隐藏容器里（保持关闭）。
    // 这样用户在需要时点 ▥▥，命令能立即被组件收到。
    ensureHiddenWidget();
    syncConversationContext();
    // 切换会话/实验上下文后立即同步给 QwenAudio 后台，
    // 避免语音的 spawn_thinking 继续写到旧会话/旧 lab_session。
    document.addEventListener('conversation-changed', syncConversationContext);
    document.addEventListener('lab:experiment-changed', syncConversationContext);
    document.addEventListener('lab:context-ready', syncConversationContext);
  });
})();
