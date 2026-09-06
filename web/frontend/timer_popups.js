/* 实验计时器面板：大弹窗展示所有计时器，支持多时钟并行。
   计时结束时自动通知 AI 系统，让 AI 知道可以推进下一步。
   轮询 /timers/active，发现完成计时器时触发通知。 */
(function () {
  var notified = {};
  var pendingShown = {};
  var startedNotified = {};
  var panelEl = null;
  var overlayEl = null;
  var createModal = null;
  var pollInterval = null;
  var lastTimers = [];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function ensureStyles() {
    if (document.getElementById('timer-panel-style')) return;
    var style = document.createElement('style');
    style.id = 'timer-panel-style';
    style.textContent = [
      /* 全屏遮罩 */
      '#timer-overlay{position:fixed;inset:0;background:rgba(15,23,42,.45);z-index:11000;display:none;align-items:center;justify-content:center;backdrop-filter:blur(2px)}',
      '#timer-overlay.show{display:flex}',
      /* 主面板 */
      '#timer-panel{background:linear-gradient(135deg,#1e3a5f 0%,#0f172a 100%);border-radius:24px;box-shadow:0 24px 80px rgba(0,0,0,.4);width:min(680px,94vw);max-height:86vh;overflow-y:auto;color:#fff;font-family:system-ui,-apple-system,sans-serif}',
      '#timer-panel-header{display:flex;align-items:center;justify-content:space-between;padding:20px 28px 16px;border-bottom:1px solid rgba(255,255,255,.1)}',
      '#timer-panel-header h2{margin:0;font-size:18px;font-weight:700;display:flex;align-items:center;gap:8px}',
      '#timer-panel-close{background:rgba(255,255,255,.1);border:0;border-radius:50%;width:32px;height:32px;color:#fff;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s}',
      '#timer-panel-close:hover{background:rgba(255,255,255,.2)}',
      '#timer-panel-body{padding:20px 28px 28px}',
      '#timer-empty{text-align:center;padding:48px 20px;color:rgba(255,255,255,.5);font-size:15px}',
      '#timer-empty .ico{font-size:48px;margin-bottom:12px;opacity:.4}',
      /* 时钟卡片 */
      '.timer-clock{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:20px;margin-bottom:16px;transition:all .3s}',
      '.timer-clock.finished{background:rgba(34,197,94,.12);border-color:rgba(34,197,94,.4);animation:timer-finished-pulse 1.5s ease-in-out infinite}',
      '.timer-clock.pending{background:rgba(59,130,246,.1);border-color:rgba(59,130,246,.3)}',
      '@keyframes timer-finished-pulse{0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,.3)}50%{box-shadow:0 0 20px 4px rgba(34,197,94,.15)}}',
      '.timer-clock-row{display:flex;align-items:center;gap:20px}',
      '.timer-clock-icon{font-size:36px;flex:0 0 auto;line-height:1}',
      '.timer-clock-info{flex:1;min-width:0}',
      '.timer-clock-label{font-size:16px;font-weight:600;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.timer-clock-meta{font-size:12px;color:rgba(255,255,255,.5)}',
      '.timer-clock-display{font-size:42px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:2px;line-height:1.2;flex:0 0 auto;text-align:right}',
      '.timer-clock.finished .timer-clock-display{color:#4ade80}',
      '.timer-clock.finished .timer-clock-icon{animation:timer-bell-shake .5s ease-in-out 3}',
      '@keyframes timer-bell-shake{0%,100%{transform:rotate(0)}25%{transform:rotate(-15deg)}75%{transform:rotate(15deg)}}',
      '.timer-clock-actions{display:flex;gap:8px;margin-top:12px}',
      '.timer-clock-btn{border:0;border-radius:10px;padding:8px 16px;font-size:13px;cursor:pointer;font-weight:500;transition:all .15s}',
      '.timer-clock-btn.dismiss{background:rgba(255,255,255,.1);color:#fff}',
      '.timer-clock-btn.dismiss:hover{background:rgba(255,255,255,.2)}',
      '.timer-clock-btn.notify{background:#2563eb;color:#fff}',
      '.timer-clock-btn.notify:hover{background:#1d4ed8}',
      '.timer-clock-btn.cancel{background:rgba(239,68,68,.15);color:#f87171}',
      '.timer-clock-btn.cancel:hover{background:rgba(239,68,68,.25)}',
      '.timer-clock-progress{height:4px;background:rgba(255,255,255,.08);border-radius:2px;margin-top:12px;overflow:hidden}',
      '.timer-clock-progress-bar{height:100%;background:linear-gradient(90deg,#3b82f6,#60a5fa);border-radius:2px;transition:width .5s linear}',
      '.timer-clock.finished .timer-clock-progress-bar{background:linear-gradient(90deg,#22c55e,#4ade80)}',
      /* 创建计时器弹窗 */
      '#timer-create-overlay{position:fixed;inset:0;background:rgba(15,23,42,.35);z-index:11500;display:none;align-items:center;justify-content:center}',
      '#timer-create-overlay.show{display:flex}',
      '#timer-create-box{background:#fff;border-radius:16px;box-shadow:0 24px 70px rgba(15,23,42,.28);padding:24px;width:min(420px,90vw);box-sizing:border-box}',
      '#timer-create-box h3{margin:0 0 16px;font-size:17px;color:#0f172a}',
      '#timer-create-box label{display:block;font-size:13px;color:#475569;margin:12px 0 6px}',
      '#timer-create-box input{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:10px 12px;font-size:15px;color:#0f172a}',
      '#timer-create-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}',
      '#timer-create-actions button{border:0;border-radius:10px;padding:10px 18px;font-size:14px;cursor:pointer;font-weight:500}',
      '#timer-create-cancel{background:#f1f5f9;color:#334155}',
      '#timer-create-ok{background:#2563eb;color:#fff}',
      /* 浮动按钮（无面板时） */
      '#timer-fab{position:fixed;right:18px;bottom:80px;z-index:10020;width:52px;height:52px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#1d4ed8);border:0;box-shadow:0 8px 24px rgba(37,99,235,.4);cursor:pointer;display:none;align-items:center;justify-content:center;font-size:22px;color:#fff;transition:transform .15s}',
      '#timer-fab:hover{transform:scale(1.08)}',
      '#timer-fab.show{display:flex}',
      '#timer-fab-badge{position:absolute;top:-4px;right:-4px;min-width:20px;height:20px;border-radius:10px;background:#ef4444;color:#fff;font-size:11px;font-weight:700;display:none;align-items:center;justify-content:center;padding:0 5px}',
      '#timer-fab-badge.show{display:flex}',
    ].join('\n');
    document.head.appendChild(style);
  }

  function formatDuration(sec) {
    sec = Math.max(0, Math.floor(sec));
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    if (h > 0) return h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
  }

  function getActiveCount(timers) {
    return timers.filter(function (t) { return !t.finished && !t.pending; }).length;
  }

  function getFinishedCount(timers) {
    return timers.filter(function (t) { return t.finished; }).length;
  }

  function renderPanel(timers) {
    ensureStyles();
    if (!panelEl) createPanel();
    var body = panelEl.querySelector('#timer-panel-body');
    if (!timers.length) {
      body.innerHTML = '<div id="timer-empty"><div class="ico">⏱</div>暂无计时器<br><span style="font-size:13px">让小科帮你计时，或者说"计时3分钟"</span></div>';
      return;
    }
    var html = '';
    timers.forEach(function (timer) {
      var cls = 'timer-clock';
      if (timer.finished) cls += ' finished';
      if (timer.pending) cls += ' pending';

      var icon = timer.finished ? '🔔' : (timer.pending ? '⏸' : '⏱');
      var remaining = timer.pending ? timer.duration_seconds : (timer.remaining_seconds || 0);
      var progressPct = timer.pending ? 0 : (timer.duration_seconds > 0 ? ((timer.duration_seconds - remaining) / timer.duration_seconds * 100) : 100);
      if (timer.finished) progressPct = 100;

      var statusText = timer.finished ? '计时结束' : (timer.pending ? '等待确认' : '计时中');
      var metaParts = [statusText];
      if (timer.duration_seconds) metaParts.push('设定 ' + formatDuration(timer.duration_seconds));

      var actions = '';
      if (timer.finished) {
        actions = '<button class="timer-clock-btn notify" data-timer-id="' + esc(timer.timer_id) + '" data-action="notify">通知小科</button>'
          + '<button class="timer-clock-btn dismiss" data-timer-id="' + esc(timer.timer_id) + '" data-action="dismiss">知道了</button>';
      } else if (!timer.pending) {
        actions = '<button class="timer-clock-btn cancel" data-timer-id="' + esc(timer.timer_id) + '" data-action="cancel">取消计时</button>';
      }

      html += '<div class="' + cls + '" data-timer-id="' + esc(timer.timer_id) + '">'
        + '<div class="timer-clock-row">'
        + '<div class="timer-clock-icon">' + icon + '</div>'
        + '<div class="timer-clock-info">'
        + '<div class="timer-clock-label">' + esc(timer.label || ('计时器 ' + timer.timer_id)) + '</div>'
        + '<div class="timer-clock-meta">' + esc(metaParts.join(' · ')) + '</div>'
        + '</div>'
        + '<div class="timer-clock-display">' + formatDuration(remaining) + '</div>'
        + '</div>'
        + '<div class="timer-clock-progress"><div class="timer-clock-progress-bar" style="width:' + progressPct + '%"></div></div>'
        + (actions ? '<div class="timer-clock-actions">' + actions + '</div>' : '')
        + '</div>';
    });
    body.innerHTML = html;

    /* 绑定按钮事件 */
    body.querySelectorAll('[data-action]').forEach(function (btn) {
      btn.onclick = function () {
        var tid = this.getAttribute('data-timer-id');
        var action = this.getAttribute('data-action');
        if (action === 'dismiss') {
          delete notified[tid];
          fetch('/timers/' + encodeURIComponent(tid), { method: 'DELETE' }).catch(function () {});
        } else if (action === 'cancel') {
          delete startedNotified[tid];
          fetch('/timers/' + encodeURIComponent(tid), { method: 'DELETE' }).catch(function () {});
        } else if (action === 'notify') {
          notifyAIFinished(tid);
        }
      };
    });
  }

  function createPanel() {
    ensureStyles();
    overlayEl = document.createElement('div');
    overlayEl.id = 'timer-overlay';
    overlayEl.innerHTML = '<div id="timer-panel">'
      + '<div id="timer-panel-header">'
      + '<h2><span>⏱</span> 实验计时器</h2>'
      + '<button id="timer-panel-close" type="button" title="收起">✕</button>'
      + '</div>'
      + '<div id="timer-panel-body"></div>'
      + '</div>';
    document.body.appendChild(overlayEl);
    panelEl = overlayEl.querySelector('#timer-panel');
    overlayEl.querySelector('#timer-panel-close').onclick = function () { hidePanel(); };
    overlayEl.addEventListener('click', function (e) { if (e.target === overlayEl) hidePanel(); });
  }

  function showPanel() {
    if (!overlayEl) createPanel();
    overlayEl.classList.add('show');
    renderPanel(lastTimers);
  }

  function hidePanel() {
    if (overlayEl) overlayEl.classList.remove('show');
  }

  function togglePanel() {
    if (!overlayEl || !overlayEl.classList.contains('show')) showPanel();
    else hidePanel();
  }

  function createFab() {
    if (document.getElementById('timer-fab')) return;
    ensureStyles();
    var fab = document.createElement('button');
    fab.id = 'timer-fab';
    fab.innerHTML = '⏱<span id="timer-fab-badge"></span>';
    fab.onclick = function () { togglePanel(); };
    document.body.appendChild(fab);
  }

  function updateFab(timers) {
    createFab();
    var fab = document.getElementById('timer-fab');
    var badge = fab.querySelector('#timer-fab-badge');
    var active = getActiveCount(timers);
    var finished = getFinishedCount(timers);
    var total = active + finished;
    if (total > 0) {
      fab.classList.add('show');
      if (finished > 0) {
        badge.textContent = finished;
        badge.classList.add('show');
      } else {
        badge.classList.remove('show');
      }
    } else {
      fab.classList.remove('show');
    }
  }

  /* 计时结束通知 AI：通过专用后端端点通知（后端会自动选语音/文字通道） */
  function notifyAIFinished(timerId) {
    var timer = lastTimers.find(function (t) { return t.timer_id === timerId; });
    if (!timer) return;
    /* 播放提示音 */
    playNotificationSound();
    /* 调用专用后端端点通知 AI */
    fetch('/timers/' + encodeURIComponent(timerId) + '/notify-ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: timer.label || '计时器', duration_seconds: timer.duration_seconds }),
    }).catch(function () {});
  }

  function closeCreateModal() {
    if (createModal) {
      createModal.classList.remove('show');
    }
  }

  function showCreateModal(timer) {
    ensureStyles();
    if (!createModal) {
      createModal = document.createElement('div');
      createModal.id = 'timer-create-overlay';
      createModal.innerHTML = '<div id="timer-create-box">'
        + '<h3>⏱ 确认计时器</h3>'
        + '<label>任务名称</label><input id="timer-create-label" maxlength="80" placeholder="例如：异丙醇静置">'
        + '<label>倒计时（秒）</label><input id="timer-create-duration" type="number" min="1" max="86400">'
        + '<div id="timer-create-actions">'
        + '<button id="timer-create-cancel" type="button">取消</button>'
        + '<button id="timer-create-ok" type="button">开始计时</button>'
        + '</div></div>';
      document.body.appendChild(createModal);
    }
    createModal.querySelector('#timer-create-label').value = timer.label || '';
    createModal.querySelector('#timer-create-duration').value = timer.duration_seconds || 60;
    createModal.classList.add('show');
    createModal.querySelector('#timer-create-cancel').onclick = function () {
      fetch('/timers/' + encodeURIComponent(timer.timer_id), { method: 'DELETE' })
        .catch(function () {})
        .finally(function () { delete pendingShown[timer.timer_id]; closeCreateModal(); });
    };
    createModal.querySelector('#timer-create-ok').onclick = function () {
      var label = createModal.querySelector('#timer-create-label').value.trim();
      var duration = parseInt(createModal.querySelector('#timer-create-duration').value, 10);
      if (!duration || duration <= 0) { alert('倒计时必须是正整数秒'); return; }
      fetch('/timers/' + encodeURIComponent(timer.timer_id) + '/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label, duration_seconds: duration }),
      }).then(function (r) { if (!r.ok) throw new Error('确认失败'); return r.json(); })
        .then(function () { delete pendingShown[timer.timer_id]; closeCreateModal(); showPanel(); })
        .catch(function (e) { alert('确认计时器失败：' + e.message); });
    };
  }

  /* 计时结束提示音：三声升调 "叮-叮-叮" */
  function playNotificationSound() {
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      var ctx = new AudioCtx();
      var notes = [880, 1108, 1318]; /* A5, C#6, E6 */
      notes.forEach(function (freq, i) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = freq;
        var start = ctx.currentTime + i * 0.22;
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.3, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, start + 0.2);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(start);
        osc.stop(start + 0.22);
      });
      /* 4 秒后自动关闭音频上下文释放资源 */
      setTimeout(function () { try { ctx.close(); } catch (_) {} }, 4000);
    } catch (_) { /* 无音频权限时静默忽略 */ }
  }

  /* 自动通知 AI 的开关：避免重复通知 */
  var autoNotified = {};

  function autoNotifyIfNeeded(timer) {
    if (autoNotified[timer.timer_id]) return;
    autoNotified[timer.timer_id] = true;
    /* 计时结束 → 播放提示音 */
    playNotificationSound();
    var label = timer.label || '计时器';
    /* 调用专用后端端点通知 AI 计时结束（后端优先走语音通道） */
    fetch('/timers/' + encodeURIComponent(timer.timer_id) + '/notify-ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: label, duration_seconds: timer.duration_seconds }),
    }).catch(function () {});
  }

  function poll() {
    fetch('/timers/active', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) return null; return r.json(); })
      .then(function (d) {
        var items = (d && d.items) || [];
        lastTimers = items;
        var seen = {};
        var hasFinished = false;
        items.forEach(function (timer) {
          seen[timer.timer_id] = true;
          if (timer.pending && !pendingShown[timer.timer_id]) {
            pendingShown[timer.timer_id] = true;
            showCreateModal(timer);
          }
          if (timer.finished && !notified[timer.timer_id]) {
            notified[timer.timer_id] = true;
            hasFinished = true;
            /* 自动通知 AI 计时结束 */
            autoNotifyIfNeeded(timer);
          }
        });
        /* 有计时器结束时自动弹出大面板 */
        if (hasFinished) showPanel();
        /* 清理已删除计时器的标记 */
        Object.keys(notified).forEach(function (id) { if (!seen[id]) delete notified[id]; });
        Object.keys(startedNotified).forEach(function (id) { if (!seen[id]) delete startedNotified[id]; });
        Object.keys(autoNotified).forEach(function (id) { if (!seen[id]) delete autoNotified[id]; });
        /* 更新浮动按钮 */
        updateFab(items);
        /* 如果面板开着，实时刷新 */
        if (overlayEl && overlayEl.classList.contains('show')) renderPanel(items);
      })
      .catch(function () { /* 网络抖动不弹错，下轮重试 */ });
  }

  function start() {
    if (window.__timerPopupsStarted) return;
    window.__timerPopupsStarted = true;
    poll();
    pollInterval = setInterval(poll, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
