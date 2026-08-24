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
      '#notify-panel{position:fixed;top:52px;right:16px;z-index:9999;width:392px;max-height:72vh;background:#fff;border:1px solid #e2e8f0;border-radius:16px;box-shadow:0 20px 52px rgba(15,23,42,.2);display:flex;flex-direction:column;overflow:hidden}',
      '#notify-panel.show{display:flex}',
      '#notify-head{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:13px 15px;border-bottom:1px solid #f1f5f9;background:#f8fbff}',
      '#notify-head b{font-size:15px;color:#0f172a}',
      '#notify-count{background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:1px 8px;font-size:11px;font-weight:600}',
      '#notify-head-actions{display:flex;align-items:center;gap:8px}',
      '#notify-readall{border:0;background:transparent;color:#2563eb;font-size:12px;cursor:pointer}',
      '#notify-close{border:0;background:transparent;font-size:18px;cursor:pointer;color:#94a3b8}',
      '#notify-list{padding:10px 12px;overflow:auto;flex:1}',
      '.notify-item{padding:11px 12px;border:1px solid #eef2f7;border-radius:12px;margin-bottom:8px;background:#fff;transition:border-color .15s}',
      '.notify-item:hover{border-color:#bfdbfe}',
      '.notify-item.unread{border-color:#dbeafe;background:#f8fbff}',
      '.notify-item .n-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:5px}',
      '.notify-item .n-period{display:inline-flex;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:600}',
      '.notify-item .n-period.morning{background:#fef3c7;color:#b45309}',
      '.notify-item .n-period.afternoon{background:#dcfce7;color:#15803d}',
      '.notify-item .n-period.evening{background:#e0e7ff;color:#4338ca}',
      '.notify-item .n-time{color:#94a3b8;font-size:11px}',
      '.notify-item .n-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:2px}',
      '.notify-item.unread .n-title{color:#1d4ed8}',
      '.notify-item .n-body{color:#64748b;font-size:12px;line-height:1.7;margin-top:4px;white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}',
      '.notify-item .n-actions{margin-top:7px;display:flex;justify-content:flex-end}',
      '.notify-item .n-actions .sh-btn{padding:2px 8px;font-size:11px}',
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
      '#detail-mask{position:fixed;inset:0;z-index:10001;background:rgba(15,23,42,.45);backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center}',
      '#detail-mask.show{display:flex}',
      '#detail-box{background:#fff;border-radius:18px;width:min(560px,94vw);max-height:85vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 28px 70px rgba(15,23,42,.35)}',
      '#detail-head{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid #f1f5f9}',
      '#detail-head b{font-size:15px;color:#0f172a}',
      '#detail-close{border:0;background:transparent;font-size:20px;cursor:pointer;color:#94a3b8}',
      '#detail-body{padding:16px 18px;overflow:auto;flex:1}',
      '#detail-body .full{background:#f8fafc;border:1px solid #eef2f7;border-radius:12px;padding:12px 14px;color:#475569;font-size:13px;line-height:1.8;white-space:pre-wrap}',
      '.todo-section-title{font-size:13px;font-weight:700;color:#0f172a;margin:16px 0 8px}',
      '.todo-row{display:flex;align-items:center;gap:10px;padding:8px 9px;border:1px solid #eef2f7;border-radius:10px;margin-bottom:6px;background:#fff}',
      '.todo-row .todo-check{width:17px;height:17px;border-radius:50%;border:1.5px solid #cbd5e1;background:#fff;cursor:pointer;flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;font-size:10px;color:#fff;transition:.15s}',
      '.todo-row.done .todo-check{background:#22c55e;border-color:#22c55e}',
      '.todo-row.done .todo-text{text-decoration:line-through;color:#94a3b8}',
      '.todo-row .todo-text{flex:1;font-size:13px;color:#334155}',
      '.todo-row .todo-edit{border:0;background:transparent;color:#64748b;cursor:pointer;font-size:13px;padding:2px 5px}',
      '.todo-row .todo-del{border:0;background:transparent;color:#b91c1c;cursor:pointer;font-size:13px;padding:2px 5px}',
      '#detail-add{display:flex;gap:8px;margin-top:10px}',
      '#detail-add input{flex:1;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px;font-size:13px;font-family:inherit}',

      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function loadNotifications() {
    return fetch('/notifications').then(function (r) { return r.json(); }).then(function (d) {
      const allItems = d.items || [];
      const items = allItems.filter(function (n) { return !n.acknowledged_at; });
      const btn = document.getElementById('sh-notify');
      const badge = document.getElementById('sh-notify-badge');
      const count = document.getElementById('notify-count');
      if (badge) badge.textContent = items.length > 99 ? '99+' : String(items.length);
      if (btn) btn.classList.toggle('has-unread', items.length > 0);
      if (count) { count.textContent = items.length; count.style.display = items.length ? '' : 'none'; }
      const list = document.getElementById('notify-list');
      if (list) {
        const periodLabel = { morning: '上午', afternoon: '下午', evening: '晚上' };
        list.innerHTML = allItems.map(function (n) {
          const unread = !n.acknowledged_at;
          const label = periodLabel[n.period] || n.period || '通知';
          return '<div class="notify-item' + (unread ? ' unread' : '') + '" data-id="' + n.id + '">'
            + '<div class="n-top"><span class="n-period ' + esc(n.period) + '">' + esc(label) + '</span><span class="n-time">' + esc(n.created_at || '') + '</span></div>'
            + '<div class="n-title">' + esc(n.title) + '</div>'
            + '<div class="n-body">' + esc(n.body) + '</div>'
            + '<div class="n-actions">' + (unread ? '<button class="sh-btn" data-ack="' + n.id + '">标记已读</button>' : '<span style="font-size:11px;color:#94a3b8">已读</span>') + '</div></div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px;padding:26px 4px;text-align:center">暂无未读通知</div>';
        Array.prototype.forEach.call(list.querySelectorAll('.notify-item'), function (item) {
          item.onclick = function (e) {
            if (e.target.closest('[data-ack]')) return;
            openDetail(item.getAttribute('data-id'));
          };
        });
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

  function closePanel() {
    const panel = document.getElementById('notify-panel');
    if (panel) panel.classList.remove('show');
  }
  function openPanel() {
    const panel = document.getElementById('notify-panel');
    if (!panel) return;
    panel.classList.add('show');
    loadNotifications();
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

  function renderTodos(todos) {
    const box = document.getElementById('detail-todos');
    if (!box) return;
    box.innerHTML = todos.map(function (todo) {
      return '<div class="todo-row' + (todo.done ? ' done' : '') + '" data-id="' + todo.id + '">'
        + '<span class="todo-check" title="标记完成">✓</span>'
        + '<span class="todo-text">' + esc(todo.text) + '</span>'
        + '<button class="todo-edit" title="修改">✎</button>'
        + '<button class="todo-del" title="删除">×</button>'
        + '</div>';
    }).join('') || '<div style="color:#94a3b8;font-size:12px">暂无待办</div>';
    Array.prototype.forEach.call(box.querySelectorAll('.todo-row'), function (row) {
      row.querySelector('.todo-check').onclick = function () {
        const id = row.getAttribute('data-id');
        const done = !row.classList.contains('done');
        fetch('/notifications/todos/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ done: done }) })
          .then(function () { openDetail(currentDetailId); });
      };
      row.querySelector('.todo-edit').onclick = function () {
        const id = row.getAttribute('data-id');
        const text = row.querySelector('.todo-text').textContent;
        const input = prompt('修改待办', text);
        if (!input || input.trim() === text) return;
        fetch('/notifications/todos/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: input.trim() }) })
          .then(function () { openDetail(currentDetailId); });
      };
      row.querySelector('.todo-del').onclick = function () {
        const id = row.getAttribute('data-id');
        if (!confirm('删除这条待办？')) return;
        fetch('/notifications/todos/' + id, { method: 'DELETE' }).then(function () { openDetail(currentDetailId); });
      };
    });
  }
  var currentDetailId = null;
  function openDetail(id) {
    currentDetailId = id;
    fetch('/notifications/' + id).then(function (r) { return r.json(); }).then(function (n) {
      document.getElementById('detail-title').textContent = n.title;
      document.getElementById('detail-full-body').textContent = n.body;
      renderTodos(n.todos || []);
      document.getElementById('detail-mask').classList.add('show');
    });
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
    panel.innerHTML = '<div id="notify-head"><b>消息通知 <span id="notify-count" style="display:none">0</span></b><div id="notify-head-actions"><button id="notify-readall">全部已读</button><button id="notify-close">×</button></div></div><div id="notify-list"></div>';
    document.body.appendChild(panel);
    const mask = document.createElement('div');
    mask.id = 'daily-mask';
    const detail = document.createElement('div');
    detail.id = 'detail-mask';
    detail.innerHTML = '<div id="detail-box"><div id="detail-head"><b>通知详情</b><button id="detail-close">×</button></div>'
      + '<div id="detail-body"><div class=""></div><div id="detail-body-text" style="display:none"></div>'
      + '<div id="detail-full-body" class="full"></div>'
      + '<div class="todo-section-title">待办清单</div><div id="detail-todos"></div>'
      + '<div id="detail-add"><input id="detail-add-input" placeholder="添加新待办…"><button class="sh-btn" id="detail-add-btn">添加</button></div>'
      + '</div></div>';
    document.body.appendChild(detail);
    document.getElementById('detail-close').onclick = function () { detail.classList.remove('show'); };
    document.getElementById('detail-add-btn').onclick = function () {
      const text = document.getElementById('detail-add-input').value.trim();
      if (!text || !currentDetailId) return;
      fetch('/notifications/' + currentDetailId + '/todos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text }) })
        .then(function () { document.getElementById('detail-add-input').value = ''; openDetail(currentDetailId); });
    };
    mask.innerHTML = '<div id="daily-box"><div id="daily-hero"><div class="ico" id="daily-hero-ico">📩</div><div><div class="t" id="daily-title"></div><div class="s" id="daily-sub"></div></div></div><button id="daily-close" type="button">×</button><div id="daily-body"></div><div id="daily-footer"><button class="sh-btn" id="daily-view">查看通知</button><button class="sh-btn primary" id="daily-ok">知道了</button></div></div>';
    document.body.appendChild(mask);

    notifyBtn.onclick = function () {
      const panel = document.getElementById('notify-panel');
      if (panel && panel.classList.contains('show')) closePanel(); else openPanel();
    };
    document.getElementById('notify-readall').onclick = function () {
      fetch('/notifications?unread=1').then(function (r) { return r.json(); }).then(function (d) {
        const ids = (d.items || []).map(function (n) { return n.id; });
        const chain = Promise.resolve();
        ids.forEach(function (id) {
          chain.then(function () { return fetch('/notifications/' + id + '/ack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); });
        });
        chain.then(function () { loadNotifications(); });
      });
    };
    document.getElementById('notify-close').onclick = function (e) { e.stopPropagation(); closePanel(); };
    document.addEventListener('click', function (e) {
      if (!e.target.closest('#notify-panel') && !e.target.closest('#sh-notify')) panel.classList.remove('show');
    });

    loadNotifications();
    ensureDailyPopup();
    setInterval(ensureDailyPopup, 60 * 1000);
    setInterval(loadNotifications, 60 * 1000);
  });
})();
