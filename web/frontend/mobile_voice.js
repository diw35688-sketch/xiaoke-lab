// 移动端语音识别（自动聆听模式）：Web Speech API（zh-CN，continuous）
//
// 数据流：页面加载即自动开始聆听 → 检测到人说话（onspeechstart，小科变聆听脸）
//   → 说完自动转写 → 转写文本显示在状态行下方，并交给 /chat
//   （由大模型工具调用 record_observation / move_step，状态仍由后端状态机判定）。
// 无需任何按钮；状态行右侧的"语音已开/已关"小开关可暂停/恢复，
// 麦克风权限被拒时也可用它重试。
//
// 兼容性说明：
//   - 桌面 Chrome / Android Chrome 可用；
//   - iPhone Safari 不支持该 API（会提示用 Chrome）；
//   - 除 localhost 外，浏览器要求 HTTPS 才允许麦克风（真机需走 HTTPS）。
(function () {
  'use strict';

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = null;
  var autoMode = true;            // 自动聆听开关
  var running = false;            // 识别会话是否在跑
  var restartTimer = null;
  var lastFinalIndex = -1;        // 连续模式下避免重复提交旧结果

  function el(id) { return document.getElementById(id); }

  function voice(kind, text) {
    if (window.MobileCards && window.MobileCards.setVoice) {
      window.MobileCards.setVoice(kind, text);
    }
  }

  function showTranscript(text) {
    var box = el('transcript-line'), span = el('transcript-text');
    if (!box || !span) return;
    if (text) { span.textContent = text; box.hidden = false; }
    else { box.hidden = true; }
  }

  function renderToggle() {
    var t = el('voice-toggle');
    if (t) {
      t.textContent = autoMode ? '语音已开' : '语音已关';
      t.classList.toggle('off', !autoMode);
    }
  }

  // 错误码 → 中文提示（Web Speech API 的标准错误码）
  var ERR_TEXT = {
    'not-allowed': '麦克风权限被拒绝：点右侧"语音已关"可重试',
    'service-not-allowed': '浏览器不允许使用语音识别服务',
    'no-speech': '没听到声音',
    'audio-capture': '找不到麦克风设备',
    'network': '语音识别服务连不上（浏览器识别需要联网）',
    'aborted': '已取消',
    'language-not-supported': '浏览器不支持中文语音识别',
  };

  function stopSession() {
    if (restartTimer) { clearTimeout(restartTimer); restartTimer = null; }
    if (rec) {
      try { rec.onend = null; rec.stop(); } catch (e) {}
      rec = null;
    }
    running = false;
  }

  function scheduleRestart() {
    if (!autoMode || running) return;
    if (restartTimer) clearTimeout(restartTimer);
    restartTimer = setTimeout(function () {
      if (autoMode && !running) startSession();
    }, 300);
  }

  function startSession() {
    if (!SR || !autoMode || running) return;
    rec = new SR();
    rec.lang = 'zh-CN';
    rec.interimResults = true;   // 边说边显示中间结果
    rec.continuous = true;       // 一直听：说一句识别一句，识别完自动继续
    lastFinalIndex = -1;

    rec.onstart = function () {
      running = true;
      voice('listening', '正在聆听…');
    };
    rec.onspeechstart = function () {
      voice('listening', '听到你在说话…');
    };
    rec.onresult = function (e) {
      var interim = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        var r = e.results[i];
        if (r.isFinal && i > lastFinalIndex) {
          lastFinalIndex = i;
          var text = String(r[0].transcript || '').trim();
          if (text.length < 2) continue;
          showTranscript(text);
          voice('thinking', 'AI 正在理解…');
          if (window.MobileCards
              && typeof window.MobileCards.submitTranscript === 'function'
              && (!window.MobileCards.isReal || window.MobileCards.isReal())) {
            window.MobileCards.submitTranscript(text);
          }
        } else if (!r.isFinal) {
          interim += r[0].transcript;
        }
      }
      if (interim) showTranscript(interim);
    };
    rec.onspeechend = function () {
      if (autoMode) voice('listening', '正在聆听…');
    };
    rec.onerror = function (e) {
      running = false;
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        autoMode = false;
        renderToggle();
        voice('idle', ERR_TEXT[e.error]);
        return;
      }
      voice('idle', ERR_TEXT[e.error] || ('识别出错：' + e.error));
      scheduleRestart();
    };
    rec.onend = function () {
      running = false;
      scheduleRestart();
    };

    try {
      rec.start();
    } catch (e) {
      voice('idle', '无法启动识别：' + e.message);
    }
  }

  function toggle() {
    autoMode = !autoMode;
    renderToggle();
    if (autoMode) {
      voice('listening', '自动聆听已开启');
      startSession();
    } else {
      stopSession();
      voice('idle', '自动聆听已关闭');
    }
  }

  function bind() {
    var t = el('voice-toggle');
    if (!t) return;
    if (!SR) {
      t.textContent = '不支持';
      t.disabled = true;
      voice('idle', '此浏览器不支持语音识别（iPhone Safari 暂不支持，请用 Chrome）');
      return;
    }
    t.onclick = toggle;
    renderToggle();
    startSession();   // 页面加载即自动聆听
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
