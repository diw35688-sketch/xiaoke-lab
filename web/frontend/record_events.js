// 实验记录实时推送：连接 /record/events (SSE)，记录一写入就刷新实验本。
// 不依赖轮询，语音/文字/工具任何路径写记录都立刻可见。
(() => {
  let es = null;
  let reconnectTimer = null;
  let reconnectDelay = 2000;

  function connect() {
    if (typeof EventSource === 'undefined') return;
    try {
      es = new EventSource('/record/events');
    } catch (_) {
      scheduleReconnect();
      return;
    }

    es.onopen = function () {
      reconnectDelay = 2000;
    };

    es.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (data.type === 'connected') return;
        if (data.type === 'record_written') {
          // 静默刷新当前视图的数据，不强制切换视图。
          // runReload 内部会判断当前是否在 run 视图才 paint，
          // chatHomeReload 同理——用户在哪页就刷哪页，不打断操作。
          if (typeof window.runReload === 'function') {
            try { window.runReload(); } catch (_) {}
          }
          if (typeof window.chatHomeReload === 'function') {
            try { window.chatHomeReload(); } catch (_) {}
          }
          // 也刷新步骤卡（步骤进度可能因记录更新）。
          if (typeof window.labStepsReload === 'function') {
            try { window.labStepsReload(); } catch (_) {}
          }
          // 如果当前在实验本视图，也刷新它。
          if (typeof window.labRecordsReload === 'function' && window.shellCurrentView && window.shellCurrentView() === 'records') {
            try { window.labRecordsReload(); } catch (_) {}
          }
          // 视觉提示：实验本有新记录了。
          try { window.dispatchEvent(new CustomEvent('lab:record-arrived', { detail: data })); } catch (_) {}
        }
      } catch (_) {}
    };

    es.addEventListener('hello', function () {
      // 连接确认，不做额外动作。
    });

    es.onerror = function () {
      try { es.close(); } catch (_) {}
      es = null;
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
      connect();
    }, reconnectDelay);
  }

  // 页面就绪后连接；切到后台再回来也重连。
  document.addEventListener('shell-ready', connect);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && (!es || es.readyState === EventSource.CLOSED)) {
      connect();
    }
  });
  // 如果 shell-ready 已触发，立即连接。
  if (document.readyState !== 'loading') {
    connect();
  }
})();
