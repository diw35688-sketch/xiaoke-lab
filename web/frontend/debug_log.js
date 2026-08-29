// 全局行为上报：把用户在前端使用的关键功能发到 /api/telemetry，便于调试。
(function () {
  var last = {};
  function send(event, data) {
    if (!event) return;
    // 简单防抖：同一事件 800ms 内只发最后一次，避免连点刷屏
    var now = Date.now();
    var key = event + ':' + JSON.stringify(data || {});
    if (last[key] && now - last[key] < 800) return;
    last[key] = now;
    try {
      fetch('/api/telemetry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: event, data: data || {} }),
      }).catch(function () {});
    } catch (err) {
      // ignore
    }
  }
  window.logAction = send;
})();
