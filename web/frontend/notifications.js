/* 消息通知 + 每日工作弹窗：创建/展示/确认均落库溯源 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function currentPeriod() {
    const h = new Date().getHours();
    if (h >= 6 && h < 12) return 'morning';
    if (h >= 12 && h < 18) return 'afternoon';
    if (h >= 18 && h < 24) return 'evening';
    return '';
  }

  function ensureStyle() {
    if (document.getElementById('notify-style')) return;
    const style = document.createElement('style');
    style.id = 'notify-style';
    style.textContent = [
      '#notify-panel{position:fixed;top:50px;right:18px;z-index:9999;width:380px;max-height:70vh;overflow:auto;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 16px 44px rgba(15,23,42,.18);display:none}',
      '#notify-panel.show{display:block}',
      '#notify-head{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;border-bottom:1px solid #f1f5f9}',
      '#notify-head b{font-size:14px;color:#0f172a}',
      '#notify-close{border:0;background:transparent;font-size:18px;cursor:pointer;color:#94a3b8}',
      '#notify-list{padding:8px 10px}',
      '.notify-item{padding:10px 8px;border-bottom:1px solid #f8fafc;font-size:12px;line-height:1.6}',
      '.notify-item .n-title{font-weight:600;color:#0f172a}',
      '.notify-item .n-meta{color:#94a3b8;font-size:11px;margin-top:3px}',
      '.notify-item .n-body{color:#475569;margin-top:5px;white-space:pre-wrap}',
      '.notify-item.unread .n-title{color:#1d4ed8}',
      '#daily-mask{position:fixed;inset:0;z-index:10000;background:rgba(15,23,42,.45);backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center}',
      '#daily-mask.show{display:flex}',
      '#daily-box{background:linear-gradient(180deg,#f8fbff 0%,#ffffff 32%);border-radius:18px;padding:0;width:min(500px,94vw);box-shadow:0 28px 70px rgba(15,23,42,.35);overflow:hidden}',
      '#daily-hero{background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;padding:18px 24px;display:flex;align-items:center;gap:12px}',
      '#daily-hero .ico{width:42px;height:42px;border-radius:12px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;font-size:22px}',
      '#daily-hero .t{font-size:17px;font-weight:700;line-height:1.3}',
      '#daily-hero .s{font-size:12px;opacity:.85;margin-top:2px}',
      '#daily-close{position:absolute;top:12px;right:14px;z-index:2;border:0;background:rgba(255,255,255,.14);color:#fff;width:26px;height:26px;border-radius:999px;cursor:pointer;font-size:14px;line-height:1}',
      '#daily-body{position:relative;padding:18px 24px 8px;font-size:13px;color:#334155;line-height:1.8;max-height:50vh;overflow:auto}',
      '#daily-body .sec{font-weight:700;color:#1e40af;margin:12px 0 6px;font-size:14px}',
      '#daily-body .row{display:flex;justify-content:space-between;gap:8px;background:#f8fafc;border:1px solid #eef2f7;border-radius:10px;padding:7px 11px;margin-bottom:5px;font-size:12px}',
      '#daily-body .row .k{color:#64748b}',
      '#daily-body .row .v{font-weight:600;color:#0f172a}',
      '#daily-footer{padding:14px 24px 20px;display:flex;justify-content:flex-end;gap:8px;background:#fff;border-top:1px solid #f1f5f9}',
      '#daily-footer .sh-btn{padding:7px 14px;border-radius:9px}',
      '#daily-footer .primary{background:#2563eb;border-color:#2563eb;color:#fff}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function loadNotifications() {
    return fetch('/notifications?unread=1').then(function (r) { return r.json(); }).then(function (d) {
      const items = d.items || [];
      const btn = document.getElementById('sh-notify');
      const badge = document.getElementById('sh-notify-badge');
      if (badge) badge.textContent = items.length > 99 ? '99+' : String(items.length);
      if (btn) btn.classList.toggle('has-unread', items.length > 0);
      const list = document.getElementById('notify-list');
      if (list) {
        list.innerHTML = items.map(function (n) {
          return '<div class="notify-item unread">'
            + '<div class="n-title">' + esc(n.title) + '</div>'
            + '<div class="n-meta">' + esc(n.created_at) + ' · ' + esc(n.period || '') + '</div>'
            + '<div class="n-body">' + esc(n.body) + '</div>'
            + '<div style="margin-top:6px"><button class="sh-btn" data-ack="' + n.id + '" style="padding:2px 8px;font-size:11px">标记已读</button></div></div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px;padding:10px 4px">暂无未读通知</div>';
        Array.prototype.forEach.call(list.querySelectorAll('[data-ack]'), function (btn) {
          btn.onclick = function () {
            fetch('/notifications/' + btn.getAttribute('data-ack') + '/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
              .then(function () { loadNotifications(); updatePanel(); });
          };
        });
      }
      return items;
    }).catch(function () { return []; });
  }

  function openPanel() {
    const panel = document.getElementById('notify-panel');
    if (!panel) return;
    panel.classList.toggle('show');
    if (panel.classList.contains('show')) loadNotifications();
  }

  function dailyBodyHtml(body) {
    const lines = String(body || '').split('\n');
    let html = '';
    lines.forEach(function (line) {
      const t = line.trim();
      if (!t) return;
      const m = t.match(/^【(.+?)】$/);
      if (m) { html += '<div class="sec">' + esc(m[1]) + '</div>'; return; }
      const kv = t.match(/^(.+?)：(.*)$/);
      if (kv) {
        html += '<div class="row"><span class="k">' + esc(kv[1]) + '</span><span class="v">' + esc(kv[2]) + '</span></div>';
        return;
      }
      html += '<div>' + esc(t) + '</div>';
    });
    return html || esc(body);
  }

  function showDaily(n) {
    const mask = document.getElementById('daily-mask');
    if (!mask) return;
    const periodLabel = { morning: '上午', afternoon: '下午', evening: '晚上' }[n.period] || '';
    const emoji = { morning: '🌅', afternoon: '☀️', evening: '🌙' }[n.period] || '📩';
    document.getElementById('daily-hero-ico').textContent = emoji;
    document.getElementById('daily-title').textContent = n.title;
    document.getElementById('daily-sub').textContent = n.period_date + (periodLabel ? ' · ' + periodLabel + '工作摘要' : '');
    document.getElementById('daily-close').style.display = 'block';
    document.getElementById('daily-body').innerHTML = dailyBodyHtml(n.body);
    mask.classList.add('show');
    const close = function () {
      mask.classList.remove('show');
      fetch('/notifications/' + n.id + '/shown', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .then(function () { loadNotifications(); });
    };
    document.getElementById('daily-close').onclick = close;
    document.getElementById('daily-ok').onclick = close;
    document.getElementById('daily-view').onclick = function () {
      close();
      openPanel();
    };
  }

  function ensureDailyPopup() {
    const period = currentPeriod();
    if (!period) return;
    fetch('/notifications/daily', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ period: period })
    }).then(function (r) { return r.json(); }).then(function (n) {
      if (n && n.id && !n.shown_at) showDaily(n);
    }).catch(function () {});
  }

  function updatePanel() {
    loadNotifications();
  }

  document.addEventListener('shell-ready', function () {
    ensureStyle();
    const notifyBtn = document.getElementById('sh-notify');
    const panel = document.createElement('div');
    panel.id = 'notify-panel';
    panel.innerHTML = '<div id="notify-head"><b>消息通知</b><button id="notify-close">×</button></div><div id="notify-list"></div>';
    document.body.appendChild(panel);
    const mask = document.createElement('div');
    mask.id = 'daily-mask';
    mask.innerHTML = '<div id="daily-box"><div id="daily-hero"><div class="ico" id="daily-hero-ico">📩</div><div><div class="t" id="daily-title"></div><div class="s" id="daily-sub"></div></div></div><button id="daily-close" type="button">×</button><div id="daily-body"></div><div id="daily-footer"><button class="sh-btn" id="daily-view">查看通知</button><button class="sh-btn primary" id="daily-ok">知道了</button></div></div>';
    document.body.appendChild(mask);

    notifyBtn.onclick = function () {
      openPanel();
    };
    document.getElementById('notify-close').onclick = function () { panel.classList.remove('show'); };
    document.addEventListener('click', function (e) {
      if (!e.target.closest('#notify-panel') && !e.target.closest('#sh-notify')) panel.classList.remove('show');
    });

    loadNotifications();
    ensureDailyPopup();
    setInterval(ensureDailyPopup, 60 * 1000);
    setInterval(loadNotifications, 60 * 1000);
  });
})();
