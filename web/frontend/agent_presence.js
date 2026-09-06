// 智能体状态条（agent presence）：小科在聊天头部的常驻席位。
// 设计合同：
//   1. 状态词表与立绘 avatar.js 完全一致（准备就绪/正在聆听/正在思考/正在回答/已完成/已暂停），
//      一套词、两个载体；立绘从此是装饰，状态条才是"能不能说话"的可靠来源。
//   2. 只订阅既有事件，不新增状态源、不改任何分发方：
//        window   'avatar-state'                —— 聆听/思考/回答/暂停
//        document 'lab:continuous-call-state'   —— 通话开关（决定"说话可打断"提示）
//        window   'lab:voice-startup-progress'  —— 语音栈准备进度；失败才转警示
//   3. 样式全部走 theme.css token，本文件零硬编码颜色（新代码不再 CSS-in-JS）。
(function () {
  'use strict';

  var LABELS = {
    idle: '准备就绪', listening: '正在聆听', thinking: '正在思考',
    speaking: '正在回答', happy: '已完成', interrupted: '已暂停'
  };
  var STARTUP_COMPONENTS = ['tts_warmup', 'silero_assets', 'microphone', 'asr_warmup'];

  var state = {
    base: 'idle',
    call: false,
    startup: {}          // component -> 'ready' | 'error' | 'pending'
  };

  function startupSummary() {
    var ready = 0, failed = false;
    STARTUP_COMPONENTS.forEach(function (key) {
      if (state.startup[key] === 'ready') ready += 1;
      if (state.startup[key] === 'error') failed = true;
    });
    return { ready: ready, total: STARTUP_COMPONENTS.length, failed: failed, done: ready === STARTUP_COMPONENTS.length };
  }

  function hintText(startup) {
    if (window.__realtimeVoiceActive === true) return '实时语音已开启';
    if (startup.failed) return ''; // 旧语音栈不可用不再干扰；实时语音由按钮独立控制
    if (!startup.done) return '语音准备中 ' + startup.ready + '/' + startup.total;
    if (state.base === 'listening') return '直接说话';
    if (state.base === 'thinking') return '稍等';
    if (state.base === 'speaking') return state.call ? '说话可打断' : '';
    if (state.base === 'idle' && state.call) return '通话中 · 直接说话';
    return '';
  }

  function render() {
    var root = document.getElementById('agent-presence');
    if (!root) return;
    var startup = startupSummary();
    var qwenActive = window.__realtimeVoiceActive === true;
    root.className = 'ap-' + state.base;
    root.querySelector('.ap-state').textContent = LABELS[state.base] || LABELS.idle;
    var extra = root.querySelector('.ap-extra');
    var hint = hintText(startup);
    extra.textContent = hint;
    extra.style.display = hint ? '' : 'none';
  }

  function mount() {
    if (document.getElementById('agent-presence')) return true;
    var head = document.getElementById('sh-chat-head');
    if (!head) return false;
    var slot = head.querySelector('span');
    if (!slot || slot.id) return false;
    slot.innerHTML = '<span id="agent-presence" role="status" aria-live="polite">'
      + '<i class="ap-dot"></i>'
      + '<span class="ap-name">小科</span>'
      + '<span class="ap-state">准备就绪</span>'
      + '<span class="ap-extra" style="display:none"></span>'
      + '</span>';
    render();
    return true;
  }

  window.addEventListener('avatar-state', function (event) {
    var next = (event.detail && event.detail.state) || event.detail;
    if (LABELS[next]) { state.base = next; render(); }
  });

  document.addEventListener('lab:continuous-call-state', function (event) {
    state.call = Boolean(event.detail && event.detail.active);
    render();
  });

  window.addEventListener('lab:realtime-voice-state', function () {
    render();
  });

  window.addEventListener('lab:voice-startup-progress', function (event) {
    var detail = event.detail || {};
    if (STARTUP_COMPONENTS.indexOf(detail.component) < 0) return;
    state.startup[detail.component] = detail.state === 'ready' ? 'ready'
      : detail.state === 'error' ? 'error' : 'pending';
    render();
  });

  document.addEventListener('shell-ready', mount);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
