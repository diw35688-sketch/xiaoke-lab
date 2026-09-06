/* 主动智能体面板：今日时间线 + 每日心跳/反思 + 论文库。 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function api(path, method, payload) {
    var options = { method: method || 'GET' };
    if (payload) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (r) { return r.json(); });
  }

  function ensureStyle() {
    if (document.getElementById('agent-panel-style')) return;
    var style = document.createElement('style');
    style.id = 'agent-panel-style';
    style.textContent = '@media(max-width:900px){.agent-grid{grid-template-columns:1fr!important}}';
    document.head.appendChild(style);
  }

  function dateInputValue(d) {
    return d.toISOString().slice(0, 10);
  }

  function renderPapers(canvas, list) {
    var host = canvas.querySelector('#agent-papers');
    if (!host) return;
    host.innerHTML = (list && list.length ? list.map(function (p) {
      return '<div style="display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px dashed #e2e8f0">'
        + '<div><div style="font-weight:600;color:#0f172a">' + esc(p.title || p.filename || ('论文 #' + p.id)) + '</div>'
        + '<div style="color:#94a3b8;font-size:11px">' + esc(p.created_at || '') + '</div></div>'
        + '<button class="sh-btn" data-paper-view="' + p.id + '" style="padding:3px 9px;font-size:12px">查看</button></div>';
    }).join('') : '<div style="color:#94a3b8;font-size:12px">还没有上传论文。</div>');
    Array.prototype.forEach.call(host.querySelectorAll('[data-paper-view]'), function (btn) {
      btn.onclick = function () {
        api('/papers/' + btn.getAttribute('data-paper-view')).then(function (p) {
          var drafts = p.drafts || [];
          var box = canvas.querySelector('#agent-paper-detail');
          if (box) {
            box.style.display = 'block';
            box.innerHTML = '<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px">' + esc(p.title || p.filename) + '</div>'
              + '<div style="font-size:12px;color:#64748b;margin-bottom:8px">' + esc(p.created_at || '') + '</div>'
              + '<div style="font-size:12px;color:#475569;white-space:pre-wrap;max-height:160px;overflow:auto;background:#f8fafc;border:1px solid #eef2f7;border-radius:10px;padding:10px">'
              + esc((p.ocr_text || '').slice(0, 2000)) + (p.ocr_text && p.ocr_text.length > 2000 ? '…' : '') + '</div>'
              + '<div style="font-size:12px;color:#64748b;margin-top:8px">识别出 ' + drafts.length + ' 份方案草稿</div>';
          }
        });
      };
    });
  }

  function renderTimeline(canvas, data) {
    var host = canvas.querySelector('#agent-timeline');
    if (!host) return;
    var records = data.records || [];
    var experiments = data.experiments || [];
    var notifications = data.notifications || [];
    var html = '';
    html += '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:12px 0 6px">实验计划</div>';
    html += experiments.length ? experiments.map(function (e) {
      return '<div style="padding:6px 0;border-bottom:1px dashed #eef2f7;display:flex;justify-content:space-between;gap:8px">'
        + '<span>' + esc(e.name) + (e.equipment ? ' <span style="color:#94a3b8;font-size:11px">' + esc(e.equipment) + '</span>' : '') + '</span>'
        + '<span style="color:#64748b;font-size:11px">' + esc(e.status || '') + '</span></div>';
    }).join('') : '<div style="color:#94a3b8;font-size:12px">今天还没有安排实验。</div>';
    html += '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:12px 0 6px">实验记录</div>';
    html += records.length ? records.map(function (r) {
      return '<div style="padding:6px 0;border-bottom:1px dashed #eef2f7">'
        + '<div style="color:#94a3b8;font-size:11px">' + esc(r.at || '') + '</div>'
        + '<div style="color:#334155;font-size:13px">' + esc(r.transcript || '') + '</div></div>';
    }).join('') : '<div style="color:#94a3b8;font-size:12px">今天还没有实验记录。</div>';
    html += '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:12px 0 6px">通知 / 心跳 / 反思</div>';
    html += notifications.length ? notifications.map(function (n) {
      return '<div style="padding:6px 0;border-bottom:1px dashed #eef2f7">'
        + '<div style="font-weight:600;color:#0f172a;font-size:13px">' + esc(n.title) + '</div>'
        + '<div style="color:#64748b;font-size:12px;white-space:pre-wrap">' + esc(n.body || '') + '</div></div>';
    }).join('') : '<div style="color:#94a3b8;font-size:12px">今天还没有心跳/反思通知。</div>';
    host.innerHTML = html;
  }

  function renderAutomations(canvas, items) {
    var host = canvas.querySelector('#agent-automations');
    if (!host) return;
    host.innerHTML = (items && items.length ? items.map(function (a) {
      var schedule = a.schedule_kind || '';
      var detail = schedule === 'cron' ? (a.cron_expr || '') : schedule === 'at' ? (a.at || '') : (a.every_ms || 0) + 'ms';
      return '<div style="display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px dashed #e2e8f0;align-items:center">'
        + '<div><div style="font-weight:600;color:#0f172a">' + esc(a.name || ('任务 #' + a.id)) + ' <span style="color:#94a3b8;font-size:11px;font-weight:400">' + esc(a.payload_kind || '') + '</span></div>'
        + '<div style="color:#64748b;font-size:11px">' + esc(detail) + ' · ' + (a.enabled ? '启用' : '停用') + ' · 下次 ' + esc(a.next_run_at || '') + '</div></div>'
        + '<button class="sh-btn" data-auto-run="' + a.id + '" style="padding:3px 9px;font-size:12px">立即运行</button></div>';
    }).join('') : '<div style="color:#94a3b8;font-size:12px">还没有自动化任务。</div>');
    Array.prototype.forEach.call(host.querySelectorAll('[data-auto-run]'), function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute('data-auto-run');
        var msg = canvas.querySelector('#agent-msg');
        btn.disabled = true;
        api('/automations/' + id + '/run', 'POST', {}).then(function (r) {
          if (msg) msg.textContent = r && r.ok ? '已执行' : (r && r.detail ? r.detail : '执行失败');
          loadAgentPanel(canvas);
        }).catch(function (e) { if (msg) msg.textContent = String(e); })
          .then(function () { btn.disabled = false; });
      };
    });
  }

  function loadAgentPanel(canvas) {
    var dateInput = canvas.querySelector('#agent-date');
    var date = dateInput ? (dateInput.value || dateInputValue(new Date())) : dateInputValue(new Date());
    Promise.all([
      api('/agent/timeline?date=' + encodeURIComponent(date)),
      api('/papers'),
      api('/automations')
    ]).then(function (out) {
      renderTimeline(canvas, out[0]);
      renderPapers(canvas, (out[1] && out[1].items) || []);
      renderAutomations(canvas, (out[2] && out[2].items) || []);
    }).catch(function () {
      var host = canvas.querySelector('#agent-timeline');
      if (host) host.innerHTML = '<div style="color:#b91c1c;font-size:13px">加载失败，请稍后重试。</div>';
    });
  }

  window.shellRegisterView('agent', function (canvas) {
    ensureStyle();
    canvas.innerHTML = '<div style="max-width:900px;margin:0 auto">'
      + '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:6px">'
      + '<span style="font-size:12px;color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:4px 10px">每日自动运行：心跳 + 反思（时间可在设置页修改）</span>'
      + '</div>'
      + '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:14px">'
      + '<button class="sh-btn" id="agent-heartbeat">立即生成今日心跳</button>'
      + '<button class="sh-btn" id="agent-reflect">立即生成今晚反思</button>'
      + '<input type="date" id="agent-date" value="' + dateInputValue(new Date()) + '" style="padding:6px 9px;border:1px solid #cbd5e1;border-radius:9px;font-size:13px;font-family:inherit">'
      + '<button class="sh-btn" id="agent-reload">刷新</button>'
      + '<span id="agent-msg" style="font-size:12px;color:#64748b"></span>'
      + '</div>'
      + '<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:14px" class="agent-grid">'
      + '<section style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px">'
      + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:4px">今日时间线</div>'
      + '<div style="font-size:12px;color:#64748b;margin-bottom:6px">实验计划 / 实验记录 / 心跳反思通知</div>'
      + '<div id="agent-timeline"></div></section>'
      + '<section style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px">'
      + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:4px">论文库</div>'
      + '<div style="font-size:12px;color:#64748b;margin-bottom:6px">上传的论文 / Protocol 文件</div>'
      + '<div id="agent-papers"></div>'
      + '<div id="agent-paper-detail" style="display:none;margin-top:10px;background:#f8fafc;border:1px solid #eef2f7;border-radius:10px;padding:10px"></div>'
      + '</section></div>'
      + '<section style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;margin-top:14px">'
      + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:4px">自动化任务（持久化 Cron）</div>'
      + '<div style="font-size:12px;color:#64748b;margin-bottom:6px">心跳/反思/定时器在这里，重启不丢，到点自动执行</div>'
      + '<div id="agent-automations"></div>'
      + '</section></div>';
    canvas.querySelector('#agent-heartbeat').onclick = function () {
      var btn = this, msg = canvas.querySelector('#agent-msg');
      btn.disabled = true; msg.textContent = '正在生成今日心跳…';
      api('/agent/heartbeat/run', 'POST', {}).then(function (r) {
        msg.textContent = r && r.ok
          ? (r.notified ? '今日心跳已生成，可在时间线通知里查看' : '没有需要打扰的事项，已静默跳过')
          : (r && r.detail ? r.detail : '失败');
        loadAgentPanel(canvas);
      }).catch(function (e) { msg.textContent = String(e); })
        .then(function () { btn.disabled = false; });
    };
    canvas.querySelector('#agent-reflect').onclick = function () {
      var btn = this, msg = canvas.querySelector('#agent-msg');
      btn.disabled = true; msg.textContent = '正在生成今晚反思…';
      api('/agent/reflect', 'POST', {}).then(function (r) {
        msg.textContent = r && r.ok
          ? (r.notified ? '今晚反思已生成，可在时间线通知里查看' : '今天还没有可反思的内容，已静默跳过')
          : (r && r.detail ? r.detail : '失败');
        loadAgentPanel(canvas);
      }).catch(function (e) { msg.textContent = String(e); })
        .then(function () { btn.disabled = false; });
    };
    canvas.querySelector('#agent-reload').onclick = function () { loadAgentPanel(canvas); };
    canvas.querySelector('#agent-date').onchange = function () { loadAgentPanel(canvas); };
    loadAgentPanel(canvas);
  });
})();
