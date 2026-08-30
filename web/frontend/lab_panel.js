// 实验方案面板：选方案 → 走步骤 → 安全提示 → 按方案确定性追问。
(function () {
  var CSS = [
    '#lab-panel{position:fixed;right:0;top:0;width:360px;height:100vh;overflow:auto;background:#fff;box-shadow:-6px 0 28px rgba(15,23,42,.16);padding:18px 20px;z-index:9990;font-size:13px;transform:translateX(100%);transition:transform .22s ease;box-sizing:border-box}','#lab-panel.open{transform:translateX(0)}','body.lab-open{padding-right:360px;transition:padding-right .22s ease}',
    '#lab-panel h3{margin:0 0 12px;font-size:15px;color:#0f172a;display:flex;justify-content:space-between;align-items:center}',
    '#lab-panel select{width:100%;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;font-family:inherit;margin-bottom:12px}',
    '.lab-step{background:#f8fafc;border-radius:10px;padding:12px;margin-bottom:10px}',
    '.lab-step-num{font-size:12px;color:#64748b;margin-bottom:4px}',
    '.lab-step-title{font-weight:600;color:#0f172a;margin-bottom:6px}',
    '.lab-step-text{color:#475569;line-height:1.6;margin-bottom:8px}',
    '.lab-tag{display:inline-block;background:#e0e7ff;color:#3730a3;border-radius:6px;padding:2px 7px;margin:2px 4px 2px 0;font-size:11px}',
    '.lab-tag.rec{background:#fef3c7;color:#92400e}',
    '.lab-safety{background:#fef2f2;border-left:3px solid #dc2626;border-radius:8px;padding:10px 12px;margin-bottom:10px}',
    '.lab-safety.mild{background:#f0fdf4;border-left-color:#16a34a}',
    '.lab-safety b{color:#b91c1c;display:block;margin-bottom:4px}',
    '.lab-safety.mild b{color:#15803d}',
    '.lab-safety p{margin:3px 0;color:#7f1d1d;line-height:1.5}',
    '.lab-safety.mild p{color:#166534}',
    '.lab-safety small{color:#94a3b8;display:block;margin-top:5px;font-size:11px}',
    '.lab-hazard{background:#fffbeb;border-radius:8px;padding:9px 11px;margin-bottom:10px;color:#92400e;line-height:1.5}',
    '.lab-nav{display:flex;gap:7px;margin-bottom:12px}',
    '.lab-nav button{flex:1;padding:7px;border:1px solid #cbd5e1;background:#fff;border-radius:8px;cursor:pointer;font-size:12px;font-family:inherit}',
    '.lab-nav button:disabled{opacity:.45;cursor:not-allowed}',
    '.lab-ask{background:#eff6ff;border-radius:10px;padding:11px 13px;color:#1e40af;line-height:1.6;margin-bottom:10px}',
    '.lab-dev{background:#fff7ed;border-radius:10px;padding:11px 13px;color:#c2410c;line-height:1.6;margin-bottom:10px}',
    '.lab-ok{background:#f0fdf4;border-radius:10px;padding:11px 13px;color:#15803d;margin-bottom:10px}',
    '#lab-toggle{position:fixed;right:16px;top:60px;z-index:9989;padding:9px 16px;border-radius:9px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;font-size:14px;font-family:inherit;box-shadow:0 2px 8px rgba(15,23,42,.08)}'
  ].join('');

  var state = null;
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }

  function renderSafety(safety, note) {
    if (!safety || !safety.length) return '';
    return safety.map(function (r) {
      var cls = r.critical ? 'lab-safety' : 'lab-safety mild';
      var head = r.critical ? ('高危试剂：' + esc(r.name)) : ('涉及试剂：' + esc(r.name));
      var cas = r.cas ? ('（CAS ' + esc(r.cas) + '）') : '';
      var body = r.critical && r.statements.length
        ? r.statements.map(function (s) { return '<p>· ' + esc(s) + '</p>'; }).join('')
        : '<p>无高危项</p>';
      var codes = r.codes && r.codes.length ? ('GHS ' + r.codes.join('/') + '　') : '';
      return '<div class="' + cls + '"><b>' + head + cas + '</b>' + body
        + '<small>' + codes + esc(note || '') + '</small></div>';
    }).join('');
  }

  function renderStep(data) {
    if (data.mode === 'free') {
      return '<div class="lab-step"><div class="lab-step-title">自由记录模式</div>'
        + '<div class="lab-step-text">未选择实验方案，系统只做记录，不产生方案性追问与安全提示。</div></div>';
    }
    var s = data.step, p = data.protocol;
    var planned = Object.keys(s.protocol_values).map(function (k) {
      return '<span class="lab-tag">' + esc(k) + '=' + esc(s.protocol_values[k]) + '</span>';
    }).join('');
    var must = s.must_record.map(function (k) {
      return '<span class="lab-tag rec">' + esc(k) + '</span>';
    }).join('');
    var hazard = s.hazard_note ? '<div class="lab-hazard">方案提示：' + esc(s.hazard_note) + '</div>' : '';
    return renderSafety(data.safety, data.safety_note)
      + hazard
      + '<div class="lab-step">'
      + '<div class="lab-step-num">步骤 ' + s.number + ' / ' + p.total_steps + '</div>'
      + '<div class="lab-step-title">' + esc(s.title) + '</div>'
      + '<div class="lab-step-text">' + esc(s.instruction) + '</div>'
      + (planned ? '<div>方案已定：' + planned + '</div>' : '')
      + (must ? '<div style="margin-top:6px">现场必测：' + must + '</div>' : '')
      + '</div>';
  }

  function paint() {
    var box = el('lab-body');
    if (!state) { box.innerHTML = ''; return; }
    box.innerHTML = renderStep(state);
    var isProtocol = state.mode === 'protocol';
    el('lab-prev').disabled = !isProtocol || state.step.number <= 1;
    el('lab-next').disabled = !isProtocol || state.step.number >= state.protocol.total_steps;
    el('lab-nav-row').style.display = isProtocol ? 'flex' : 'none';
  }

  function api(path, method, payload) {
    var options = { method: method || 'GET' };
    if (payload) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (r) { return r.json(); });
  }

  function loadSession() {
    var path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session')
      : '/protocols/session';
    return api(path).then(function (d) { state = d; paint(); return d; });
  }

  // 供语音链路调用：拿到实体后做确定性判断并显示结果
  window.labEvaluate = function (entities) {
    return api('/protocols/evaluate', 'POST', { entities: entities || {} })
      .then(function (d) {
        var box = el('lab-result');
        var html = '';
        if (d.follow_up_required) {
          html += '<div class="lab-ask">小科追问：' + esc(d.follow_up_question) + '</div>';
        } else if (state && state.mode === 'protocol') {
          html += '<div class="lab-ok">本步现场记录已完整</div>';
        }
        (d.deviations || []).forEach(function (x) {
          html += '<div class="lab-dev">偏差：' + esc(x.field) + ' 实际为 ' + esc(x.actual_value)
            + '，方案规定为 ' + esc(x.protocol_value) + ' —— 请确认是否有意调整</div>';
        });
        box.innerHTML = html;
        return d;
      });
  };

  window.labCurrentStep = function () { return state; };

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var panel = document.createElement('div');
    panel.id = 'lab-panel';
    panel.innerHTML = '<h3>实验方案<button id="lab-hide" style="border:0;background:transparent;cursor:pointer;color:#94a3b8;font-size:18px">-</button></h3>'
      + '<select id="lab-select"><option value="">自由记录模式（不选方案）</option></select>'
      + '<div class="lab-nav" id="lab-nav-row" style="display:none">'
      + '<button id="lab-prev">上一步</button><button id="lab-next">下一步</button></div>'
      + '<div id="lab-body"></div><div id="lab-result"></div>';
    document.body.appendChild(panel);

    var toggle = document.createElement('button');
    toggle.id = 'lab-toggle';
    toggle.textContent = '实验方案 / 安全';
    document.body.appendChild(toggle);

    function setOpen(open) {
      panel.classList.toggle('open', open);
      document.body.classList.toggle('lab-open', open);
      toggle.style.display = open ? 'none' : 'block';
    }
    el('lab-hide').onclick = function () { setOpen(false); };
    toggle.onclick = function () { setOpen(true); };
    // 默认收起，不遮挡聊天区；选了方案后自动展开
    setOpen(false);
    window.labOpenPanel = function () { setOpen(true); };

    api('/protocols').then(function (d) {
      var select = el('lab-select');
      (d.protocols || []).forEach(function (p) {
        var option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.title + '（' + p.total_steps + ' 步）';
        select.appendChild(option);
      });
      return loadSession();
    }).catch(function () {});

    el('lab-select').onchange = function (e) {
      var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
      api('/protocols/session', 'POST', {
        protocol_id: e.target.value || null,
        conversation_id: ids.conversation_id || null,
        lab_session_id: ids.lab_session_id || null,
      })
        .then(function (d) { state = d; el('lab-result').innerHTML = ''; paint(); });
    };
    el('lab-prev').onclick = function () {
      window.moveProtocolStep('prev')
        .then(function (d) { state = d; el('lab-result').innerHTML = ''; paint(); })
        .catch(function (error) { el('lab-result').textContent = error.message; });
    };
    el('lab-next').onclick = function () {
      window.moveProtocolStep('next')
        .then(function (d) { state = d; el('lab-result').innerHTML = ''; paint(); })
        .catch(function (error) { el('lab-result').textContent = error.message; });
    };
  }

  // 面板默认收起、labRender 时才展开；lab-result 是记录回执的渲染目标，必须存在。
  init();
})();

// 渲染一次完整记录结果：转写、抽取的实体、确定性判断
(function () {
  function esc2(s) { return String(s == null ? '' : s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }
  window.labRender = function (d) {
    var box = document.getElementById('lab-result');
    if (!box) return;
    if (window.labOpenPanel) window.labOpenPanel();
    var html = '<div class="lab-step"><div class="lab-step-num">第 ' + d.segment_id + ' 段口述</div>'
      + '<div class="lab-step-text">' + esc2(d.transcript) + '</div>';
    var ents = d.entities || {};
    var filled = Object.keys(ents).filter(function (k) { return ents[k]; });
    if (filled.length) {
      html += '<div>抽取实体：' + filled.map(function (k) {
        return '<span class="lab-tag">' + esc2(k) + '=' + esc2(ents[k]) + '</span>';
      }).join('') + '</div>';
    }
    html += '</div>';
    // B4：渲染 messages（前端只按 kind 上样式，不判断内容；话术来自后端 copy 层）
    var msgs = d.messages || [];
    msgs.forEach(function (m) {
      if (m.kind === 'clarification') {
        // 去 copy 层的"小科："前缀，面板标签已用"小科追问"表达称呼，避免重复
        var q = String(m.text || '').replace(/^小科：/, '');
        html += '<div class="lab-ask">小科追问：' + esc2(q) + '</div>';
      } else if (m.kind === 'record_ack') {
        html += '<div class="lab-ok">' + esc2(m.text) + '</div>';
      } else {
        html += '<div>' + esc2(m.text) + '</div>';
      }
    });
    box.innerHTML = html;
  };
})();
