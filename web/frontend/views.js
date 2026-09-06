// 把原先散落的悬浮面板，改造成应用外壳里的正式页面与详情区内容。
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }
  function ensureCardStyles() {
    if (document.getElementById('card-grid-style')) return;
    var style = document.createElement('style');
    style.id = 'card-grid-style';
    style.textContent = [
      '.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-top:12px}',
      '.card-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:10px 12px;margin-bottom:12px}',
      '.card-toolbar input[type=search]{flex:1;min-width:180px;box-sizing:border-box;padding:8px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.card-toolbar input[type=search]:focus{outline:2px solid rgba(59,103,232,.25);border-color:#3b67e8}',
      '.card-toolbar .sh-btn{white-space:nowrap}',
      // 社区同款搜索框/分类按钮
      '.com-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:12px;margin-bottom:12px}',
      '.com-toolbar input,.com-toolbar select{padding:9px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.com-toolbar input{flex:1;min-width:160px}',
      '.com-cats{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}',
      '.com-cat{padding:6px 12px;border:1px solid #e2e8f0;background:#fff;color:#475569;border-radius:999px;cursor:pointer;font-size:12px;font-family:inherit;transition:all .12s}',
      '.com-cat:hover{background:#f1f5f9}',
      '.com-cat.active{background:#2563eb;border-color:#2563eb;color:#fff}',
      '.p-card,.reagent-card,.record-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;cursor:pointer;transition:border-color .15s,box-shadow .15s;position:relative}',
      '.p-card:hover,.reagent-card:hover,.record-card:hover{border-color:#3b67e8;box-shadow:0 4px 12px rgba(59,103,232,.08)}',
      '.p-card.active{border-color:#2563eb;box-shadow:0 0 0 2px #bfdbfe}',
      '.card-tip{color:#64748b;font-size:12px;margin:8px 0 4px}',
      '.card-empty{color:#94a3b8;font-size:13px;margin:20px 0}',
      '.search-note{font-size:12px;color:#64748b;margin:8px 0 0}',
      '@media(max-width:900px){.card-grid{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }
  function shortHazardCodes(codes) {
    if (!codes || !codes.length) return '';
    if (codes.length <= 2) return codes.join('/');
    return codes.slice(0, 2).join('/') + ' 等 ' + codes.length + ' 项';
  }
  function api(path, method, payload) {
    var options = { method: method || 'GET' };
    if (payload) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (r) { return r.json(); });
  }

  var session = null;

  function interactionStatusLabel(protocolSession) {
    var snapshot = window.interactionModeState?.capture('text');
    if (!snapshot || snapshot.interaction_mode === 'chat') return '自由聊天';
    if (snapshot.experiment_context === 'free') return '自由实验记录';
    if (snapshot.experiment_context === 'protocol') {
      return protocolSession && protocolSession.mode === 'protocol' && protocolSession.protocol
        ? esc(protocolSession.protocol.title) + ' · 第 ' + protocolSession.step.number
          + '/' + protocolSession.protocol.total_steps + ' 步'
        : '方案实验';
    }
    if (snapshot.experiment_context === 'template') return '模板实验';
    if (snapshot.experiment_context === 'storage') return '实验存储';
    return '实验模式';
  }
  window.interactionStatusLabel = interactionStatusLabel;

  // ---------- 顶栏状态 ----------
  function refreshStatus() {
    var protocolPath = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session')
      : '/protocols/session';
    Promise.all([api('/settings'), api(protocolPath)]).then(function (out) {
      var s = out[0], p = out[1];
      session = p;
      var bits = [];
      bits.push(s.ready
        ? '<span class="sh-pill ok">模型已配置</span>'
        : '<span class="sh-pill warn">未配置模型</span>');
      bits.push('<span class="sh-pill">' + interactionStatusLabel(p) + '</span>');
      window.shellStatus(bits.join(''));
      if (window.runReload) window.runReload();
    }).catch(function () {});
  }
  window.shellRefreshStatus = refreshStatus;

  // ---------- 计算器页：分子量 / 溶液配制 / 稀释 ----------
  window.shellRegisterView('calculator', function (host) {
    var examples = ['CuSO4·5H2O', '(NH4)2SO4', 'Ca(OH)2', 'KAl(SO4)2·12H2O', 'FeSO4·7H2O', 'Na2CO3·10H2O', 'C6H12O6', '五水硫酸铜'];
    var tabs = [
      { id: 'mw', label: '分子量' },
      { id: 'prep', label: '溶液配制' },
      { id: 'dilute', label: '稀释计算' }
    ];
    host.innerHTML = '<div style="max-width:820px;margin:0 auto">'
      + '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px 22px">'
      + '<div style="display:flex;gap:6px;border-bottom:1px solid #e2e8f0;margin-bottom:18px">'
      + tabs.map(function (t) { return '<button class="calc-tab" data-tab="' + t.id + '" style="border:0;background:transparent;padding:8px 14px;font-size:14px;color:#64748b;cursor:pointer;border-bottom:2px solid transparent">' + t.label + '</button>'; }).join('')
      + '</div>'
      // 分子量
      + '<div class="calc-pane" data-pane="mw">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:4px">分子量 / 摩尔质量计算</div>'
      + '<div style="color:#64748b;font-size:13px;margin-bottom:16px">输入试剂中文名、英文名或化学式，支持括号、复盐、结晶水合物。</div>'
      + '<div style="display:flex;gap:10px"><input id="calc-input" style="flex:1;min-width:0;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:15px;font-family:inherit" placeholder="例如：CuSO4·5H2O、五水硫酸铜、KAl(SO4)2·12H2O">'
      + '<button id="calc-run" class="sh-btn primary" style="padding:10px 18px">计算</button></div>'
      + '<div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px">' + examples.map(function (e) {
          return '<button class="calc-example" data-value="' + esc(e) + '" style="border:1px solid #e2e8f0;background:#f8fafc;border-radius:999px;padding:4px 10px;font-size:12px;color:#334155;cursor:pointer">' + esc(e) + '</button>';
        }).join('') + '</div>'
      + '<div id="calc-result" style="margin-top:16px"></div>'
      + '</div>'
      // 溶液配制
      + '<div class="calc-pane" data-pane="prep" style="display:none">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:4px">溶液配制计算</div>'
      + '<div style="color:#64748b;font-size:13px;margin-bottom:16px">按 质量(g) = 浓度(mol/L) × 体积(L) × 分子量(g/mol) 计算称样量，支持纯度修正。</div>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">'
      + '<div><label style="font-size:12px;color:#475569">试剂 / 化学式</label><input id="prep-reagent" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：NaOH、Tris、CuSO4·5H2O"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标浓度 (mol/L)</label><input id="prep-molarity" type="number" step="any" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：0.1"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标体积</label><div style="display:flex;gap:6px;margin-top:4px"><input id="prep-volume" type="number" step="any" style="flex:1;min-width:0;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="500"><select id="prep-volume-unit" style="padding:9px 8px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px"><option value="mL">mL</option><option value="L">L</option></select></div></div>'
      + '<div><label style="font-size:12px;color:#475569">纯度 (%)</label><input id="prep-purity" type="number" step="any" value="100" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px"></div>'
      + '</div>'
      + '<button id="prep-run" class="sh-btn primary" style="padding:9px 18px">计算称样量</button>'
      + '<div id="prep-result" style="margin-top:14px"></div>'
      + '</div>'
      // 稀释计算
      + '<div class="calc-pane" data-pane="dilute" style="display:none">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:4px">稀释计算</div>'
      + '<div style="color:#64748b;font-size:13px;margin-bottom:16px">按 C1V1 = C2V2 计算需要取多少母液。</div>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">'
      + '<div><label style="font-size:12px;color:#475569">母液浓度</label><input id="dil-stock" type="number" step="any" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：1"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标浓度</label><input id="dil-target" type="number" step="any" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：0.1"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标体积</label><div style="display:flex;gap:6px;margin-top:4px"><input id="dil-volume" type="number" step="any" style="flex:1;min-width:0;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="500"><select id="dil-volume-unit" style="padding:9px 8px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px"><option value="mL">mL</option><option value="L">L</option></select></div></div>'
      + '</div>'
      + '<button id="dil-run" class="sh-btn primary" style="padding:9px 18px">计算取液量</button>'
      + '<div id="dil-result" style="margin-top:14px"></div>'
      + '</div>'
      + '</div>'
      + '<div style="color:#94a3b8;font-size:12px;margin-top:14px;line-height:1.8">计算引擎：molmass（开源 BSD-3）优先，内置解析器兜底；试剂名先查试剂安全库（PubChem）。</div>'
      + '</div>';

    function renderError(box, d, fallback) {
      box.innerHTML = '<div style="background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:10px;padding:12px 14px;font-size:13px">' + esc((d && d.detail) || fallback || '计算失败') + '</div>';
    }

    function renderMw(d) {
      var box = host.querySelector('#calc-result');
      if (!d || d.detail) { renderError(box, d); return; }
      var nameLine = d.name ? '<div style="font-size:13px;color:#64748b;margin-bottom:2px">' + esc(d.name) + '</div>' : '';
      box.innerHTML = '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px 18px">'
        + nameLine
        + '<div style="font-size:20px;font-weight:800;color:#166534">' + esc(d.formula || '-') + '</div>'
        + '<div style="font-size:26px;font-weight:800;color:#0f172a;margin-top:8px">' + Number(d.molecular_weight).toFixed(3) + ' <span style="font-size:14px;color:#64748b;font-weight:400">g/mol</span></div>'
        + '<div style="font-size:12px;color:#64748b;margin-top:8px">来源：' + esc(d.source || '化学式解析') + '</div>'
        + '</div>';
    }

    function runMw(value) {
      var v = String(value || '').trim();
      if (!v) return;
      var box = host.querySelector('#calc-result');
      box.innerHTML = '<div style="color:#94a3b8;font-size:13px">计算中…</div>';
      api('/calculator/molecular-weight', 'POST', { reagent: v }).then(renderMw).catch(function (err) {
        renderError(box, { detail: err.message || err }, '请求失败');
      });
    }

    function renderPrep(d) {
      var box = host.querySelector('#prep-result');
      if (!d || d.detail) { renderError(box, d); return; }
      box.innerHTML = '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px 18px">'
        + '<div style="font-size:13px;color:#64748b">' + esc(d.name || d.formula) + ' · 分子量 ' + Number(d.molecular_weight).toFixed(3) + ' g/mol</div>'
        + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin:8px 0 4px">' + Number(d.molarity) + ' mol/L × ' + Number(d.volume) + ' ' + esc(d.volume_unit) + '</div>'
        + '<div style="font-size:26px;font-weight:800;color:#166534">' + Number(d.mass_g).toFixed(4) + ' g</div>'
        + '<div style="font-size:13px;color:#64748b;margin-top:4px">（' + Number(d.mass_mg).toFixed(2) + ' mg）' + (d.purity !== 100 ? ' · 已按纯度 ' + Number(d.purity) + '% 修正' : '') + '</div>'
        + '<div style="font-size:13px;color:#334155;margin-top:10px">' + esc(d.instruction) + '</div>'
        + '</div>';
    }

    function runPrep() {
      var box = host.querySelector('#prep-result');
      box.innerHTML = '<div style="color:#94a3b8;font-size:13px">计算中…</div>';
      var payload = {
        reagent: host.querySelector('#prep-reagent').value,
        molarity: parseFloat(host.querySelector('#prep-molarity').value),
        volume: parseFloat(host.querySelector('#prep-volume').value),
        volume_unit: host.querySelector('#prep-volume-unit').value,
        purity: parseFloat(host.querySelector('#prep-purity').value || 100)
      };
      api('/calculator/solution-prep', 'POST', payload).then(renderPrep).catch(function (err) {
        renderError(box, { detail: err.message || err }, '请求失败');
      });
    }

    function renderDil(d) {
      var box = host.querySelector('#dil-result');
      if (!d || d.detail) { renderError(box, d); return; }
      box.innerHTML = '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px;padding:16px 18px">'
        + '<div style="font-size:15px;font-weight:700;color:#0f172a">取母液 <span style="font-size:26px;color:#166534">' + Number(d.stock_volume).toFixed(4) + '</span> ' + esc(d.volume_unit) + '</div>'
        + '<div style="font-size:13px;color:#64748b;margin-top:6px">再加溶剂定容至 ' + Number(d.final_volume) + ' ' + esc(d.volume_unit) + '</div>'
        + '<div style="font-size:13px;color:#334155;margin-top:10px">' + esc(d.instruction) + '</div>'
        + '</div>';
    }

    function runDil() {
      var box = host.querySelector('#dil-result');
      box.innerHTML = '<div style="color:#94a3b8;font-size:13px">计算中…</div>';
      var payload = {
        stock_concentration: parseFloat(host.querySelector('#dil-stock').value),
        final_concentration: parseFloat(host.querySelector('#dil-target').value),
        final_volume: parseFloat(host.querySelector('#dil-volume').value),
        volume_unit: host.querySelector('#dil-volume-unit').value
      };
      api('/calculator/dilution', 'POST', payload).then(renderDil).catch(function (err) {
        renderError(box, { detail: err.message || err }, '请求失败');
      });
    }

    function activateTab(id) {
      Array.prototype.forEach.call(host.querySelectorAll('.calc-tab'), function (tab) {
        var active = tab.dataset.tab === id;
        tab.style.color = active ? '#1d4ed8' : '#64748b';
        tab.style.borderBottomColor = active ? '#2563eb' : 'transparent';
        tab.style.fontWeight = active ? '600' : '400';
      });
      Array.prototype.forEach.call(host.querySelectorAll('.calc-pane'), function (pane) {
        pane.style.display = pane.dataset.pane === id ? '' : 'none';
      });
    }

    host.querySelector('#calc-run').onclick = function () { runMw(host.querySelector('#calc-input').value); };
    host.querySelector('#calc-input').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); runMw(this.value); }
    });
    Array.prototype.forEach.call(host.querySelectorAll('.calc-example'), function (btn) {
      btn.onclick = function () {
        var value = btn.dataset.value;
        host.querySelector('#calc-input').value = value;
        runMw(value);
      };
    });
    host.querySelector('#prep-run').onclick = runPrep;
    host.querySelector('#dil-run').onclick = runDil;
    Array.prototype.forEach.call(host.querySelectorAll('.calc-tab'), function (tab) {
      tab.onclick = function () { activateTab(tab.dataset.tab); };
    });
    activateTab('mw');
  });

  // ---------- AI 排程弹窗 ----------
  function showAIScheduleModal(parentHost, schedule, protocolIds, onDone) {
    ensureCardStyles();
    var modalBg = document.createElement('div');
    modalBg.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.45);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box';

    function tagList(items, color) {
      if (!items || !items.length) return '<span style="color:#94a3b8;font-size:12px">无</span>';
      return items.map(function (it) {
        return '<span style="display:inline-block;background:' + (color || '#dbeafe') + ';color:' + (color === '#fef3c7' ? '#92400e' : '#1e40af') + ';padding:2px 8px;border-radius:6px;font-size:12px;margin:2px">' + esc(typeof it === 'string' ? it : (it.name || '')) + '</span>';
      }).join('');
    }

    var scheduleHtml = (schedule.length ? schedule : [{ order: 1, protocol_id: '', title: '等待排程...', produces: [], requires: [], missing: [], rationale: '', depends_on: [] }]).map(function (item) {
      var depText = (item.depends_on && item.depends_on.length) ? '依赖实验 ' + item.depends_on.join(',') : '无前置依赖';
      return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:10px">'
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
        + '<div style="width:32px;height:32px;border-radius:50%;background:#2563eb;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px">' + (item.order || '?') + '</div>'
        + '<div style="flex:1">'
        + '<div style="font-weight:600;color:#0f172a;font-size:14px">' + esc(item.title || '') + '</div>'
        + '<div style="font-size:12px;color:#64748b">' + depText
        + (item.estimated_minutes ? ' · 预计 ' + item.estimated_minutes + ' 分钟' : '')
        + (item.wait_hours ? ' · 等待 ' + item.wait_hours + ' 小时' : '')
        + '</div></div></div>'
        + '<div style="margin:8px 0"><span style="font-size:12px;color:#64748b;font-weight:600">产出: </span>' + tagList(item.produces, '#dbeafe') + '</div>'
        + '<div style="margin:8px 0"><span style="font-size:12px;color:#64748b;font-weight:600">需要: </span>' + tagList(item.requires, '#f0fdf4') + '</div>'
        + (item.missing && item.missing.length ? '<div style="margin:8px 0"><span style="font-size:12px;color:#b91c1c;font-weight:600">缺料: </span>' + tagList(item.missing, '#fef3c7') + '</div>' : '')
        + (item.rationale ? '<div style="margin:8px 0 0;padding:8px 10px;background:#f8fafc;border-radius:8px;font-size:12px;color:#475569">💡 ' + esc(item.rationale) + '</div>' : '')
        + '</div>';
    }).join('');

    // 连接线（简单的顺序箭头）
    var chainHint = schedule.length > 1
      ? '<div style="text-align:center;font-size:12px;color:#94a3b8;margin:4px 0 12px">↕ 实验按依赖顺序排列，上方实验的产物可作为下方实验的材料</div>'
      : '';

    modalBg.innerHTML = '<div style="background:#fff;border-radius:16px;max-width:720px;width:100%;max-height:85vh;overflow-y:auto;padding:24px 28px;box-shadow:0 20px 60px rgba(0,0,0,.2)">'
      + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
      + '<span style="font-size:20px">🧬</span>'
      + '<span style="font-weight:700;font-size:18px;color:#0f172a">AI 智能排程</span>'
      + '</div>'
      + '<div style="font-size:13px;color:#64748b;margin-bottom:16px">分析了 ' + schedule.length + ' 个实验的生物学依赖关系和材料链</div>'
      + chainHint
      + scheduleHtml
      + '<div style="display:flex;gap:10px;margin-top:16px;padding-top:16px;border-top:1px solid #e2e8f0">'
      + '<button class="sh-btn primary" id="ai-schedule-confirm" style="flex:1">✓ 确认创建计划</button>'
      + '<button class="sh-btn" id="ai-schedule-cancel">取消</button>'
      + '</div></div>';

    document.body.appendChild(modalBg);

    modalBg.querySelector('#ai-schedule-cancel').onclick = function () {
      document.body.removeChild(modalBg);
    };
    modalBg.onclick = function (e) {
      if (e.target === modalBg) document.body.removeChild(modalBg);
    };

    modalBg.querySelector('#ai-schedule-confirm').onclick = function () {
      var btn = this;
      btn.disabled = true;
      btn.textContent = '创建中…';
      api('/planning/create-plan', 'POST', { protocol_ids: protocolIds }).then(function (res) {
        if (res && res.detail) {
          btn.textContent = '失败：' + res.detail;
          btn.disabled = false;
          return;
        }
        var created = res.created || [];
        var schedule = res.schedule || [];
        var count = created.length;
        document.body.removeChild(modalBg);
        if (onDone) onDone();

        if (count === 0) {
          alert('计划创建失败，请重试。');
          return;
        }

        // 找到排程里的第一个实验（order 最小）
        var first = created[0];
        var firstSchedule = (first && first.schedule_info) || schedule[0] || {};
        var firstPid = firstSchedule.protocol_id || (first && first.notes && first.notes.match(/protocol_id=([^;\s]+)/));
        if (firstPid && typeof firstPid === 'object') firstPid = firstPid[1];
        if (!firstPid) firstPid = protocolIds[0];
        var firstName = first ? first.name : (firstSchedule.title || '');

        // 构建排程摘要给聊天上下文
        var scheduleLines = schedule.map(function (s) {
          var deps = (s.depends_on && s.depends_on.length) ? '（依赖实验 ' + s.depends_on.join(',') + '）' : '';
          var mins = s.estimated_minutes ? ' · 约' + s.estimated_minutes + '分钟' : '';
          return (s.order || '?') + '. ' + (s.title || '') + deps + mins;
        });
        var scheduleSummary = scheduleLines.join('\n');

        // 进入第一个实验
        if (window.interactionModeState) window.interactionModeState.select('protocol', firstPid);
        var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
        api('/protocols/session', 'POST', {
          protocol_id: firstPid,
          conversation_id: ids.conversation_id || null,
          lab_session_id: ids.lab_session_id || null,
        }).then(function () {
          if (window.refreshStatus) window.refreshStatus();
          window.shellShow('run');
          if (window.composerRefresh) window.composerRefresh();
          if (window.labStepsReload) window.labStepsReload();
          // 把排程上下文发给右侧聊天
          if (window.composerSend) {
            var msg = '我通过 AI 排程制定了 ' + count + ' 个实验的执行计划：\n' + scheduleSummary +
              '\n\n现在开始第一个实验「' + firstName + '」，请简要说明第一步怎么做，需要哪些试剂和仪器。';
            window.composerSend(msg);
          }
        });
      }).catch(function (e) {
        btn.textContent = '失败：' + e.message;
        btn.disabled = false;
      });
    };
  }

  // ---------- 实验方案页 ----------
  window.shellRegisterView('protocols', function (host) {
    api('/protocols').then(function (d) {
      ensureCardStyles();
      var protocolPageSize = 10000;
      var selectedProtocols = {};
      var protocolCat = '';
      var protocolSort = 'latest';
      function protocolCatLabel(source) {
        var s = source || '';
        if (!s) return '未分类';
        if (/protocols\.io/i.test(s)) return 'protocols.io';
        if (/本科/.test(s)) return '本科实验教学';
        if (/国内/.test(s) || /重点实验室/.test(s)) return '实验室方案';
        if (/社区/.test(s)) return '社区模板';
        if (/pdf|翻译|复核/i.test(s)) return 'PDF 导入';
        return s.length > 14 ? s.slice(0, 14) + '…' : s;
      }
      function protocolMark(text, q) {
        var safe = esc(text);
        if (!q) return safe;
        var escaped = String(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return safe.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
      }
      function startProtocol(id, title) {
        // 先切到协议/自由实验模式，protocolSessionIdentity 才会返回
        // 真正用于实验 Turn 的 lab_session_id。
        window.interactionModeState.select(id ? 'protocol' : 'free', id || null);
        var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
        api('/protocols/session', 'POST', {
          protocol_id: id || null,
          conversation_id: ids.conversation_id || null,
          lab_session_id: ids.lab_session_id || null,
        }).then(function () {
          refreshStatus();
          // 开始方案后直接进“实验进行中”，不经过空白的聊天首页。
          window.shellShow(id ? 'run' : 'chat');
          if (window.composerRefresh) window.composerRefresh();
          if (window.labStepsReload) window.labStepsReload();
          // 把开始实验的上下文自动发给会话，Agent 能直接接手当前方案。
          if (window.composerSend) {
            if (id && title) {
              window.composerSend('我现在开始执行方案「' + title + '」，请简要说明第一步怎么做、需要哪些试剂和仪器。');
            } else {
              window.composerSend('已进入自由记录模式，开始记录实验操作。');
            }
          }
        });
      }
      host.innerHTML = '<div class="com-toolbar">'
        + '<span style="font-weight:700;font-size:14px;color:#0f172a">📋 实验方案</span>'
        + '<input type="search" id="protocol-search" placeholder="搜索方案名称 / 来源…" autocomplete="off" spellcheck="false" name="noname-protocol-search">'
        + '<select id="protocol-sort"><option value="latest">最新</option><option value="steps">步骤最多</option><option value="title">名称</option></select>'
        + '<button class="sh-btn primary" id="protocol-chat-create">AI 创建</button>'
        + '<button class="sh-btn" id="protocol-file-btn">选择文件</button>'
        + '<button class="sh-btn" id="protocol-order-btn">AI 排程并加入计划</button>'
        + '<input type="file" id="protocol-file" accept=".json,.pdf,.png,.jpg,.jpeg" style="display:none">'
        + '<span id="protocol-file-msg" style="font-size:12px;color:#64748b"></span>'
        + '<span id="protocol-order-msg" style="font-size:12px;color:#64748b"></span>'
        + '</div>'
        + '<div class="search-note">文件自动识别：JSON 直接入库；PDF/图片走 OCR 识别成方案</div>'
        + '<div class="com-cats" id="protocol-cats"></div>'
        + '<div id="protocol-summary" style="font-size:12px;color:#64748b;margin:2px 0 10px"></div>'
        + '<div id="protocol-grid" class="card-grid"></div>'
        + '<div id="protocol-more-box" style="margin-top:10px;text-align:center"></div>'
        + '<div id="ai-draft-box"></div>'
        + '<div id="ocr-draft-box"></div>';

      function renderProtocols(items, all, q) {
        if (protocolCat) items = items.filter(function (p) { return protocolCatLabel(p.source) === protocolCat; });
        if (protocolSort === 'steps') {
          items = items.slice().sort(function (a, b) { return (b.total_steps || 0) - (a.total_steps || 0); });
        } else if (protocolSort === 'title') {
          items = items.slice().sort(function (a, b) { return (a.title || '').localeCompare(b.title || '', 'zh'); });
        } else {
          items = items.slice();
        }
        // 分类按钮：按来源生成短标签，跟随社区样式
        var catBox = host.querySelector('#protocol-cats');
        if (catBox) {
          var sources = {};
          (all || []).forEach(function (p) {
            var label = protocolCatLabel(p.source);
            sources[label] = (sources[label] || 0) + 1;
          });
          var keys = Object.keys(sources).sort(function (a, b) { return sources[b] - sources[a]; }).slice(0, 12);
          catBox.innerHTML = '<button class="com-cat' + (!protocolCat ? ' active' : '') + '" data-cat="">全部</button>'
            + keys.map(function (s) {
              return '<button class="com-cat' + (protocolCat === s ? ' active' : '') + '" data-cat="' + esc(s) + '">' + esc(s) + ' (' + sources[s] + ')</button>';
            }).join('');
          Array.prototype.forEach.call(catBox.querySelectorAll('[data-cat]'), function (btn) {
            btn.onclick = function () {
              protocolCat = btn.getAttribute('data-cat');
              Array.prototype.forEach.call(catBox.querySelectorAll('[data-cat]'), function (b) { b.classList.toggle('active', b === btn); });
              var lower = q || '';
              var filtered = (all || []).filter(function (p) {
                if (protocolCat && protocolCatLabel(p.source) !== protocolCat) return false;
                if (!lower) return true;
                return (p.title || '').toLowerCase().indexOf(lower) >= 0 || (p.source || '').toLowerCase().indexOf(lower) >= 0;
              });
              renderProtocols(filtered, all, lower);
            };
          });
        }
        var visible = items.slice(0, protocolPageSize);
        var cards = visible.map(function (p) {
          var on = session && session.mode === 'protocol' && session.protocol.id === p.id;
          return '<div class="p-card' + (on ? ' active' : '') + '" data-id="' + p.id + '" data-title="' + esc(p.title) + '">'
            + '<label style="float:right;margin-left:8px;cursor:pointer" title="点菜加入今日计划"><input type="checkbox" data-select-id="' + p.id + '"' + (selectedProtocols[p.id] ? ' checked' : '') + ' /></label>'
            + '<div style="font-weight:600;color:#0f172a;margin-bottom:5px">' + protocolMark(p.title, q)
            + (on ? '<span style="color:#2563eb;font-size:12px;margin-left:8px">进行中</span>' : '') + '</div>'
            + '<div style="color:#64748b;font-size:12px;line-height:1.6">共 ' + p.total_steps + ' 步 · ' + protocolMark(p.source, q) + '</div>'
            + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-view-detail="' + p.id + '" style="padding:3px 9px;font-size:12px">查看方案</button>'
            + (p.deletable ? '<button class="sh-btn" type="button" data-del-protocol="' + p.id + '" data-title="' + esc(p.title) + '" style="margin-left:6px;padding:3px 9px;font-size:12px;color:#b91c1c">删除</button>' : '')
            + '</div></div>';
        }).join('');
        var freeActive = session && session.mode === 'free';
        var grid = host.querySelector('#protocol-grid');
        grid.innerHTML = '<div class="p-card' + (freeActive ? ' active' : '') + '" data-id="" data-title="自由记录模式">'
          + '<div style="font-weight:600;color:#0f172a">自由记录模式</div>'
          + '<div style="color:#64748b;font-size:12px;margin-top:4px">不按方案，只做记录，不产生方案性追问</div>'
          + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-view-detail="" style="padding:3px 9px;font-size:12px">进入</button></div></div>'
          + cards || '<div class="card-empty">没有匹配的方案。</div>';
        Array.prototype.forEach.call(grid.querySelectorAll('.p-card'), function (card) {
          card.onclick = function (e) {
            if (e.target.closest('[data-view-detail]')) return;
            if (!card.dataset.id) {
              startProtocol('', '自由记录模式');
              return;
            }
            // 点方案卡片先看方案详情，由用户决定是否开始实验；不再立刻跳到聊天。
            showProtocolDetail(host, card.dataset.id);
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-view-detail]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-view-detail');
            if (!id) {
              startProtocol('', '自由记录模式');
              return;
            }
            showProtocolDetail(host, id);
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-del-protocol]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-del-protocol');
            var title = btn.getAttribute('data-title') || '该方案';
            if (!confirm('确定删除方案「' + title + '」？此操作不可恢复。')) return;
            api('/protocols/' + encodeURIComponent(id), 'DELETE').then(function (res) {
              if (res && res.detail) { alert('删除失败：' + res.detail); return; }
              api('/protocols').then(function (d) {
                protocolPageSize = 10000;
                renderProtocols(d.protocols || [], d.protocols || [], '');
              });
            }).catch(function (err) {
              alert('删除失败：' + err.message);
            });
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-select-id]'), function (cb) {
          cb.onclick = function (e) { e.stopPropagation(); };
          cb.onchange = function () {
            var id = cb.getAttribute('data-select-id');
            if (cb.checked) selectedProtocols[id] = true;
            else delete selectedProtocols[id];
            var msg = host.querySelector('#protocol-order-msg');
            var count = Object.keys(selectedProtocols).length;
            if (msg) msg.textContent = count ? '已点 ' + count + ' 个实验' : '';
          };
        });
        var summary = host.querySelector('#protocol-summary');
        summary.textContent = '共 ' + items.length + ' 份方案' + (q ? '，命中 ' + items.length + ' 份' : '');
        var moreBox = host.querySelector('#protocol-more-box');
        if (items.length > protocolPageSize) {
          moreBox.innerHTML = '<button class="sh-btn" id="protocol-more" style="padding:5px 14px">显示全部 ' + items.length + ' 份</button>';
          var moreBtn = moreBox.querySelector('#protocol-more');
          moreBtn.onclick = function () {
            protocolPageSize = items.length;
            renderProtocols(items, all, q);
            moreBox.innerHTML = '';
          };
        } else {
          moreBox.innerHTML = '';
        }
      }
      protocolPageSize = 10000;
      renderProtocols(d.protocols || [], d.protocols || [], '');
      var sortSelect = host.querySelector('#protocol-sort');
      if (sortSelect) {
        sortSelect.onchange = function () {
          protocolSort = sortSelect.value;
          var q = host.querySelector('#protocol-search').value.trim().toLowerCase();
          var filtered = (d.protocols || []).filter(function (p) {
            return !q || (p.title || '').toLowerCase().indexOf(q) >= 0 || (p.source || '').toLowerCase().indexOf(q) >= 0;
          });
          renderProtocols(filtered, d.protocols || [], q);
        };
      }
      var searchInput = host.querySelector('#protocol-search');
      searchInput.addEventListener('input', function () {
        var q = searchInput.value.trim().toLowerCase();
        protocolPageSize = 10000;
        renderProtocols((d.protocols || []).filter(function (p) {
          return !q || (p.title || '').toLowerCase().indexOf(q) >= 0 || (p.source || '').toLowerCase().indexOf(q) >= 0;
        }), d.protocols || [], q);
      });
      var chatCreate = host.querySelector('#protocol-chat-create');
      if (chatCreate) chatCreate.onclick = function () {
        var message = document.getElementById('message');
        if (message) {
          message.value = '请根据我的描述创建一份新的实验方案：';
          message.focus();
          message.setSelectionRange(message.value.length, message.value.length);
        }
      };
      var fileBtn = host.querySelector('#protocol-file-btn');
      if (fileBtn) fileBtn.onclick = function () { fileInput.click(); };
      var fileInput = host.querySelector('#protocol-file');
      if (fileInput) fileInput.onchange = function () {
        var file = fileInput.files && fileInput.files[0];
        var msg = host.querySelector('#protocol-file-msg');
        var box = host.querySelector('#ocr-draft-box');
        if (!file) return;
        var name = (file.name || '').toLowerCase();
        if (name.endsWith('.json')) {
          msg.textContent = 'JSON 上传中…';
          var reader = new FileReader();
          reader.onload = function () {
            try {
              var data = JSON.parse(reader.result);
              var payload = { protocols: data.protocols || [data] };
              api('/protocols/upload', 'POST', payload).then(function (res) {
                if (res && res.detail) { msg.textContent = '上传失败：' + res.detail; return; }
                msg.textContent = '已新增 ' + (res.added || 0) + ' 份方案';
                window.shellShow('protocols');
              }).catch(function (e) { msg.textContent = '上传失败：' + e.message; });
            } catch (e) { msg.textContent = 'JSON 解析失败：' + e.message; }
          };
          reader.readAsText(file);
          return;
        }
        if (/\.(pdf|png|jpg|jpeg)$/.test(name)) {
          msg.textContent = 'OCR 识别中，可能需要 1-2 分钟…';
          box.innerHTML = '';
          var form = new FormData();
          form.append('file', file);
          fetch('/papers/upload', { method: 'POST', body: form }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
          }).then(function (res) {
            if (!res.ok) { msg.textContent = res.d.detail || '识别失败'; return; }
            var drafts = res.d.drafts || [];
            msg.textContent = '已存入论文库，识别出 ' + drafts.length + ' 个实验，请逐个确认保存';
            box.innerHTML = drafts.map(function (draft, index) {
              return '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px;margin-top:10px">'
                + esc(JSON.stringify(draft, null, 2)) + '</pre>'
                + '<div style="margin-top:8px"><button class="sh-btn primary" data-ocr-save="' + index + '">确认保存此方案</button></div>';
            }).join('');
            Array.prototype.forEach.call(box.querySelectorAll('[data-ocr-save]'), function (btn) {
              btn.onclick = function () {
                btn.disabled = true;
                api('/protocols/save-draft', 'POST', { protocol: drafts[parseInt(btn.dataset.ocrSave, 10)] }).then(function (saved) {
                  if (saved && saved.detail) { btn.textContent = '保存失败：' + saved.detail; btn.disabled = false; return; }
                  btn.textContent = '已保存';
                  window.shellShow('protocols');
                });
              };
            });
          }).catch(function (e) { msg.textContent = '识别失败：' + e.message; });
          return;
        }
        msg.textContent = '不支持的文件类型';
      };

      var orderBtn = host.querySelector('#protocol-order-btn');
      if (orderBtn) orderBtn.onclick = function () {
        var ids = Object.keys(selectedProtocols);
        if (!ids.length) {
          var msg = host.querySelector('#protocol-order-msg');
          if (msg) msg.textContent = '请先勾选要排程的实验';
          return;
        }
        orderBtn.disabled = true;
        var msg = host.querySelector('#protocol-order-msg');
        if (msg) msg.textContent = 'AI 排程中，分析实验依赖和材料链…';
        api('/planning/ai-schedule', 'POST', { protocol_ids: ids }).then(function (res) {
          if (res && res.detail) {
            if (msg) msg.textContent = '排程失败：' + res.detail;
            return;
          }
          showAIScheduleModal(host, res.schedule || [], ids, function () {
            orderBtn.disabled = false;
            selectedProtocols = {};
            renderProtocols((d.protocols || []), (d.protocols || []), '');
          });
        }).catch(function (e) {
          if (msg) msg.textContent = '排程失败：' + e.message;
        }).then(function () {
          orderBtn.disabled = false;
        });
      };

      Array.prototype.forEach.call(host.querySelectorAll('.p-card'), function (card) {
        card.onclick = function () {
          startProtocol(card.dataset.id, card.dataset.title);
        };
      });

      function showProtocolDetail(host, protocolId) {
        api('/protocols/' + encodeURIComponent(protocolId)).then(function (d) {
          var steps = (d.steps || []).map(function (s) {
            var values = Object.keys(s.protocol_values || {}).map(function (k) {
              return '<span style="background:#e0e7ff;color:#3730a3;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;display:inline-block;font-size:11px">'
                + esc(k) + '=' + esc(s.protocol_values[k]) + '</span>';
            }).join('');
            var must = (s.must_record || []).join('、') || '无';
            var safety = (s.safety || []).map(function (x) {
              return '<div style="margin-top:6px;color:#b91c1c;font-size:12px">⚠ ' + esc(x.name) + '：' + esc((x.statements || []).join('；')) + '</div>';
            }).join('');
            return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;margin-bottom:10px">'
              + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px">'
              + '<div style="font-weight:600;color:#0f172a">第 ' + s.number + ' 步 · ' + esc(s.title) + '</div>'
              + '<div style="white-space:nowrap"><button class="sh-btn step-edit" data-step="' + s.number + '" style="margin-left:4px;padding:3px 8px;font-size:12px">编辑</button>'
              + '<button class="sh-btn step-del" data-step="' + s.number + '" style="margin-left:4px;padding:3px 8px;font-size:12px;color:#b91c1c">删除</button></div></div>'
              + '<div style="color:#334155;font-size:13px;line-height:1.7">' + esc(s.instruction) + '</div>'
              + (values ? '<div style="margin-top:8px">方案已定：' + values + '</div>' : '')
              + '<div style="margin-top:8px;color:#64748b;font-size:12px">现场必测：' + esc(must) + '</div>'
              + (s.hazard_note ? '<div style="margin-top:8px;color:#b45309;font-size:12px">方案提示：' + esc(s.hazard_note) + '</div>' : '')
              + safety
              + '</div>'
              + '<div style="text-align:center;margin-bottom:10px"><button class="sh-btn step-add" data-after="' + s.number + '" style="border:1px dashed #cbd5e1;background:transparent;padding:4px 12px;font-size:12px">+ 在此后添加步骤</button></div>';
          }).join('');
          var preps = (d.prep_requirements || []).map(function (p) {
            return '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:9px 12px;margin-bottom:8px">'
              + '<b>' + esc(p.name_zh) + '</b> · ' + esc(p.target_concentration || '工作液')
              + '<div style="color:#475569;font-size:12px;margin-top:3px">' + esc(p.purpose) + '</div></div>';
          }).join('');
          host.innerHTML = '<div style="max-width:820px">'
            + '<button class="sh-btn" id="protocol-back">← 返回方案列表</button>'
            + '<div style="margin:14px 0 4px;font-size:18px;font-weight:700;color:#0f172a">' + esc(d.protocol.title) + '</div>'
            + '<div style="color:#64748b;font-size:12px;margin-bottom:14px">' + esc(d.protocol.source) + ' · 共 ' + d.protocol.total_steps + ' 步 · v' + esc(d.protocol.version) + '</div>'
            + '<div style="margin-bottom:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap"><button class="sh-btn primary" id="protocol-select-detail" style="padding:12px 28px;font-size:15px;font-weight:700;border-radius:12px">▶ 选择此方案开始实验</button>'
            + '<button class="sh-btn" id="protocol-checklist" style="margin-left:8px">生成准备清单</button>'
            + '<button class="sh-btn" id="protocol-edit-detail" style="margin-left:8px">编辑当前步骤</button>'
            + (d.protocol.deletable ? '<button class="sh-btn" id="protocol-delete-detail" style="margin-left:8px;color:#b91c1c">🗑 删除此方案</button>' : '')
            + '</div>'
            + '<div id="protocol-checklist-box" style="display:none;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:14px"></div>'
            + (preps ? '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:0 0 8px">实验前准备</div>' + preps : '')
            + '<div style="margin-top:18px;border-top:1px dashed #cbd5e1;padding-top:14px;background:#f8fafc;border-radius:12px;padding:12px 14px">'
            + '<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:5px">使用右侧 AI 助手修改</div>'
            + '<div style="font-size:12px;color:#64748b;line-height:1.7">同一个聊天框可以查看、添加、修改、删除方案步骤，也能控制页面。方案上下文会通过工具读取，不再维护第二个 AI 输入框。</div>'
            + '<button class="sh-btn primary" id="protocol-chat-edit" style="margin-top:8px">在对话中修改这个方案</button></div>'
            + '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:10px 0 8px">实验步骤</div>'
            + steps + '</div>';
          var chatEdit = host.querySelector('#protocol-chat-edit');
          if (chatEdit) chatEdit.onclick = function () {
            var message = document.getElementById('message');
            if (message) {
              message.value = '请查看方案 ' + protocolId + '，根据我的要求修改它：';
              message.focus();
              message.setSelectionRange(message.value.length, message.value.length);
            }
          };

          var checklistBtn = host.querySelector('#protocol-checklist');
          var checklistBox = host.querySelector('#protocol-checklist-box');
          if (checklistBtn && checklistBox) {
            checklistBtn.onclick = function () {
              checklistBtn.disabled = true;
              checklistBtn.textContent = '生成中…';
              api('/checklists/generate', 'POST', { protocol_id: protocolId }).then(function (res) {
                if (res && res.detail) {
                  checklistBox.style.display = 'block';
                  checklistBox.innerHTML = '<b style="color:#b91c1c">生成失败：</b>' + esc(res.detail);
                  return;
                }
                checklistBox.style.display = 'block';
                function listItems(items, fallback) {
                  if (!items || !items.length) return '<div style="color:#94a3b8;font-size:12px">' + fallback + '</div>';
                  return items.map(function (it) {
                    if (it.name) {
                      var status = it.found_in_storage
                        ? '<span style="color:#047857;font-size:11px">库存有</span>'
                        : '<span style="color:#dc2626;font-size:11px">库存缺</span>';
                      return '<div style="display:flex;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px dashed #eef2f7">'
                        + '<span>' + esc(it.name) + '</span>' + status + '</div>';
                    }
                    return '<div style="padding:6px 0;border-bottom:1px dashed #eef2f7">' + esc(it) + '</div>';
                  }).join('');
                }
                var missing = (res.missing_reagents || []).map(function (m) { return m.name; });
                checklistBox.innerHTML = '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">实验前准备清单</div>'
                  + '<div style="font-size:12px;color:#64748b;margin-bottom:10px">' + esc(res.protocol_title) + ' · 共 ' + res.total_steps + ' 步'
                  + (missing.length ? ' · <b style="color:#dc2626">缺 ' + missing.length + ' 种试剂</b>' : '') + '</div>'
                  + '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:10px 0 5px">试剂 / 溶液</div>'
                  + listItems(res.reagents, '未识别到明确试剂，可手动补充。')
                  + '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:10px 0 5px">仪器</div>'
                  + listItems(res.equipment, '未识别到明确仪器。')
                  + '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:10px 0 5px">耗材</div>'
                  + listItems(res.consumables, '未识别到明确耗材。')
                  + '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:10px 0 5px">安全提示</div>'
                  + listItems((res.safety || []).map(function (s) { return '第' + s.step + '步：' + s.note; }), '该方案没有额外安全提示。')
                  + (res.prep_requirements && res.prep_requirements.length
                    ? '<div style="font-size:13px;font-weight:700;color:#1e40af;margin:10px 0 5px">需提前配制</div>'
                      + res.prep_requirements.map(function (p) {
                        return '<div style="padding:6px 0;border-bottom:1px dashed #eef2f7">' + esc(p.name_zh) + ' · ' + esc(p.target_concentration || '') + '</div>';
                      }).join('')
                    : '');
              }).catch(function (e) {
                checklistBox.style.display = 'block';
                checklistBox.innerHTML = '<b style="color:#b91c1c">生成失败：</b>' + esc(e.message);
              }).then(function () {
                checklistBtn.disabled = false;
                checklistBtn.textContent = '生成准备清单';
              });
            };
          }

          Array.prototype.forEach.call(host.querySelectorAll('.step-add'), function (btn) {
            btn.onclick = function () {
              var after = parseInt(btn.dataset.after, 10);
              var title = prompt('新步骤标题（插在第 ' + after + ' 步之后）');
              if (!title) return;
              api('/protocols/step', 'POST', { protocol_id: protocolId, after_step_number: after, title: title, instruction: '请补充步骤说明', must_record: [], terms: [] }).then(function (res) {
                if (res && res.detail) { alert('添加失败：' + res.detail); return; }
                showProtocolDetail(host, protocolId);
              });
            };
          });
          Array.prototype.forEach.call(host.querySelectorAll('.step-edit'), function (btn) {
            btn.onclick = function () {
              var stepNumber = parseInt(btn.dataset.step, 10);
              api('/protocols/session', 'POST', { protocol_id: protocolId }).then(function () {
                return api('/protocols/session/move', 'POST', { action: 'jump', step_number: stepNumber });
              }).then(function () {
                refreshStatus();
                setTimeout(function () { if (window.openProtocolEditor) window.openProtocolEditor(); }, 200);
              });
            };
          });
          Array.prototype.forEach.call(host.querySelectorAll('.step-del'), function (btn) {
            btn.onclick = function () {
              var stepNumber = parseInt(btn.dataset.step, 10);
              if (!confirm('确定删除第 ' + stepNumber + ' 步？此操作会立即落盘。')) return;
              api('/protocols/step', 'DELETE', { protocol_id: protocolId, step_number: stepNumber }).then(function (res) {
                if (res && res.detail) { alert('删除失败：' + res.detail); return; }
                showProtocolDetail(host, protocolId);
              });
            };
          });
          host.querySelector('#protocol-back').onclick = function () { window.shellShow('protocols'); };
          var deleteDetail = host.querySelector('#protocol-delete-detail');
          if (deleteDetail) deleteDetail.onclick = function () {
            if (!confirm('确定删除方案「' + d.protocol.title + '」？此操作不可恢复。')) return;
            deleteDetail.disabled = true;
            deleteDetail.textContent = '删除中…';
            api('/protocols/' + encodeURIComponent(protocolId), 'DELETE').then(function (res) {
              if (res && res.detail) { alert('删除失败：' + res.detail); deleteDetail.disabled = false; deleteDetail.textContent = '🗑 删除此方案'; return; }
              window.shellShow('protocols');
            }).catch(function (err) {
              alert('删除失败：' + err.message);
              deleteDetail.disabled = false;
              deleteDetail.textContent = '🗑 删除此方案';
            });
          };
          host.querySelector('#protocol-select-detail').onclick = function () {
            window.interactionModeState.select('protocol', protocolId);
            var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
            api('/protocols/session', 'POST', {
              protocol_id: protocolId,
              conversation_id: ids.conversation_id || null,
              lab_session_id: ids.lab_session_id || null,
            }).then(function () {
              refreshStatus();
              window.shellShow('run');
              if (window.runReload) window.runReload();
              window.composerSend('我现在开始执行方案「' + d.protocol.title + '」（共 ' + d.protocol.total_steps + ' 步），请简要说明第一步怎么做、需要哪些试剂和仪器。');
            });
          };
          host.querySelector('#protocol-edit-detail').onclick = function () {
            window.shellShow('run');
            setTimeout(function () { if (window.openProtocolEditor) window.openProtocolEditor(); }, 300);
          };
        }).catch(function (err) {
          host.innerHTML = '<div style="color:#b91c1c;font-size:13px">加载方案详情失败：' + esc(err.message || err) + '</div>';
        });
      }
        var aiTextBtn = host.querySelector('#ai-protocol-text-btn');
        if (aiTextBtn) aiTextBtn.onclick = function () {
          var text = host.querySelector('#protocol-text').value.trim();
          if (!text) { alert('请先粘贴实验步骤文字'); return; }
          var box = host.querySelector('#ai-draft-box');
          box.innerHTML = '<p style="color:#64748b;font-size:12px">AI 正在分析文字…</p>';
          api('/protocols/ai-draft', 'POST', { text: text }).then(function (d) {
            if (d && d.detail) throw new Error(d.detail);
            box.innerHTML = '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px">'
              + esc(JSON.stringify(d, null, 2)) + '</pre>'
              + '<div style="margin-top:10px"><button class="sh-btn primary" id="ai-draft-save">确认保存此方案</button></div>'
              + '<p id="ai-draft-msg" style="color:#64748b;font-size:12px;margin-top:8px"></p>';
            host.querySelector('#ai-draft-save').onclick = function () {
              api('/protocols/save-draft', 'POST', { protocol: d }).then(function (res) {
                var msg = host.querySelector('#ai-draft-msg');
                if (res && res.detail) { msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + res.detail; return; }
                msg.style.color = '#15803d'; msg.textContent = '方案已保存，已自动识别关联试剂';
                window.shellShow('protocols');
              });
            };
          }).catch(function (err) {
            box.innerHTML = '<p style="color:#c2410c;font-size:12px">AI 分析失败：' + (err.message || err) + '</p>';
          });
        };

        var aiBtn = host.querySelector('#ai-protocol-btn');
        if (aiBtn) aiBtn.onclick = function () {
          var text = prompt('用自然语言描述你想做的实验，例如：配制100mL 0.1M pH7.4磷酸盐缓冲液');
          if (!text) return;
          var box = host.querySelector('#ai-draft-box');
          box.innerHTML = '<p style="color:#64748b;font-size:12px">AI 正在生成方案草稿…</p>';
          api('/protocols/ai-draft', 'POST', { text: text }).then(function (d) {
            if (d && d.detail) throw new Error(d.detail);
            box.innerHTML = '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px">'
              + esc(JSON.stringify(d, null, 2)) + '</pre>'
              + '<div style="margin-top:10px"><button class="sh-btn primary" id="ai-draft-save">确认保存此方案</button><span style="color:#94a3b8;font-size:12px;margin-left:10px">保存前会经过严格契约校验</span></div>'
                + '<p id="ai-draft-msg" style="color:#64748b;font-size:12px;margin-top:8px"></p>';
              var saveBtn = host.querySelector('#ai-draft-save');
              saveBtn.onclick = function () {
                saveBtn.disabled = true;
                api('/protocols/save-draft', 'POST', { protocol: d }).then(function (res) {
                  var msg = host.querySelector('#ai-draft-msg');
                  if (res && res.detail) { msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + res.detail; return; }
                  msg.style.color = '#15803d'; msg.textContent = '方案已保存';
                  if (window.shellRegisterView) window.shellShow('protocols');
                  if (window.runReload) window.runReload();
                  refreshStatus();
                }).catch(function (err) {
                  var msg = host.querySelector('#ai-draft-msg');
                  msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + (err.message || '未知错误');
                }).then(function () { saveBtn.disabled = false; });
              };
          }).catch(function (err) {
            box.innerHTML = '<p style="color:#c2410c;font-size:12px">生成失败：' + esc(err.message || '未知错误') + '</p>';
          });
        };
    });
  });

  // ---------- 试剂安全库页 ----------
  window.shellRegisterView('reagents', function (host) {
    api('/protocols/reagents').then(function (d) {
      ensureCardStyles();
      host.innerHTML = '<div class="card-toolbar">'
        + '<input type="search" id="reagent-search" placeholder="搜索试剂名称 / CAS / 分子式…" autocomplete="off">'
        + '<span style="font-size:12px;color:#64748b">共 ' + d.count + ' 种试剂</span>'
        + '</div>'
        + '<div class="search-note">' + esc(d.note || '') + '</div>'
        + '<div id="reagent-grid" class="card-grid"></div>';

      function renderReagents(items) {
        var grid = host.querySelector('#reagent-grid');
        grid.innerHTML = items.map(function (r) {
          return '<div class="reagent-card" data-name="' + esc(r.name) + '">'
            + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b>' + esc(r.name) + '</b>'
            + (r.critical
                ? '<span title="' + esc((r.codes || []).join('/')) + '" style="background:#fee2e2;color:#b91c1c;border-radius:999px;padding:2px 9px;font-size:11px;white-space:nowrap;max-width:170px;overflow:hidden;text-overflow:ellipsis">高危 ' + esc(shortHazardCodes(r.codes)) + '</span>'
                : '<span style="color:#94a3b8;font-size:12px">无高危项</span>') + '</div>'
            + '<div style="color:#64748b;font-size:12px;margin-top:5px">CAS ' + esc(r.cas || '—') + ' · ' + esc(r.formula || '') + '</div>'
            + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-reagent-detail="' + esc(r.name) + '" style="padding:3px 9px;font-size:12px">查看详情</button></div></div>';
        }).join('') || '<div class="card-empty">没有匹配的试剂。</div>';
        Array.prototype.forEach.call(grid.querySelectorAll('.reagent-card'), function (card) {
          card.onclick = function (e) {
            if (e.target.closest('[data-reagent-detail]')) return;
            var item = (d.reagents || []).filter(function (r) { return r.name === card.dataset.name; })[0];
            if (item) showReagentDetail(item);
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-reagent-detail]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var item = (d.reagents || []).filter(function (r) { return r.name === btn.getAttribute('data-reagent-detail'); })[0];
            if (item) showReagentDetail(item);
          };
        });
      }
      renderReagents(d.reagents || []);
      var searchInput = host.querySelector('#reagent-search');
      searchInput.addEventListener('input', function () {
        var q = searchInput.value.trim().toLowerCase();
        renderReagents((d.reagents || []).filter(function (r) {
          if (!q) return true;
          return (r.name || '').toLowerCase().indexOf(q) >= 0 || (r.cas || '').toLowerCase().indexOf(q) >= 0 || (r.formula || '').toLowerCase().indexOf(q) >= 0;
        }));
      });

      function showReagentDetail(item) {
        var statements = (item.statements || []).map(function (s) {
          return '<div style="padding:5px 0;border-bottom:1px solid #f1f5f9;color:#334155;font-size:13px">' + esc(s) + '</div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px">无 GHS 危险性说明记录</div>';
        var critical = (item.critical_statements || []).map(function (s) {
          return '<div style="padding:4px 0;color:#b91c1c;font-size:12px">⚠ ' + esc(s) + '</div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px">无高危项</div>';
        host.innerHTML = '<div style="max-width:760px">'
          + '<button class="sh-btn" id="reagent-back">← 返回试剂列表</button>'
          + '<div style="margin:14px 0 4px;font-size:18px;font-weight:700;color:#0f172a">' + esc(item.name) + '</div>'
          + '<div style="color:#64748b;font-size:12px;margin-bottom:14px">' + esc(item.name_en || '') + ' · CAS ' + esc(item.cas || '—') + ' · ' + esc(item.formula || '') + ' · ' + esc(item.signal_word || '') + '</div>'
          + '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;margin-bottom:12px"><div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px">GHS 危险性说明</div>' + statements + '</div>'
          + '<div style="background:#fff;border:1px solid #fee2e2;border-radius:12px;padding:13px 15px;margin-bottom:12px"><div style="font-size:13px;font-weight:700;color:#b91c1c;margin-bottom:6px">现场重点提醒</div>' + critical + '</div>'
          + '<div style="font-size:12px;color:#94a3b8">复核状态：' + esc(item.review_status || 'UNREVIEWED') + (item.source_url ? ' · <a href="' + esc(item.source_url) + '" target="_blank">PubChem 来源</a>' : '') + '</div>'
          + '</div>';
        host.querySelector('#reagent-back').onclick = function () { window.shellShow('reagents'); };
      }

      Array.prototype.forEach.call(host.querySelectorAll('.reagent-card'), function (card) {
        card.onclick = function () {
          var item = (d.reagents || []).filter(function (r) { return r.name === card.dataset.name; })[0];
          if (item) showReagentDetail(item);
        };
      });
    });
  });

  // ---------- 实验本：每个实验会话一本完整记录 ----------
  var notebookDetailSession = null;

  function fmtClock(at) {
    if (!at) return '';
    var d = new Date(String(at).length === 10 ? at.replace(' ', 'T') + 'Z' : at);
    if (isNaN(d.getTime())) return String(at).slice(11, 16);
    var h = String(d.getHours()).padStart(2, '0');
    var m = String(d.getMinutes()).padStart(2, '0');
    return h + ':' + m;
  }
  function fmtDate(at) {
    if (!at) return '';
    var d = new Date(String(at).length === 10 ? at.replace(' ', 'T') + 'Z' : at);
    if (isNaN(d.getTime())) return String(at).slice(0, 10);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function reloadRecords() {
    var host = window.shellCanvas ? window.shellCanvas() : document.getElementById('sh-canvas');
    if (!host) return;

    if (notebookDetailSession) {
      loadSessionDetail(notebookDetailSession);
      return;
    }
    loadSessionList();
  }

  function loadSessionList() {
    var host = window.shellCanvas ? window.shellCanvas() : document.getElementById('sh-canvas');
    host.innerHTML = '<div style="max-width:880px;margin:0 auto;padding:8px 0">'
      + '<div style="font-size:18px;font-weight:700;color:var(--n-900,#0f172a);margin-bottom:4px">实验本</div>'
      + '<div style="color:var(--n-500,#64748b);font-size:13px;margin-bottom:18px">所有实验记录按会话归档，点击查看完整实验过程。</div>'
      + '<div id="nb-list" style="color:var(--n-500)>正在加载…</div>'
      + '</div>';

    api('/record/sessions').then(function (data) {
      var sessions = data.sessions || [];
      var container = host.querySelector('#nb-list');
      if (!sessions.length) {
        container.innerHTML = '<div style="color:var(--n-500);font-size:13px;padding:40px 20px;text-align:center;background:var(--n-00);border:1px dashed var(--bd-2);border-radius:14px">'
          + '还没有实验记录。<br>开始一个实验方案后，口述的操作和数据会自动记录到这里。</div>';
        return;
      }

      var html = sessions.map(function (s) {
        var protoBadge = s.protocol_title
          ? '<span style="display:inline-block;background:var(--brand-50,#eff6ff);color:var(--brand-strong,#2563eb);border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600">' + esc(s.protocol_title) + '</span>'
          : '<span style="color:var(--n-400);font-size:11px">自由实验</span>';
        var stepInfo = s.total_steps
          ? '第 ' + s.current_step_number + ' / ' + s.total_steps + ' 步'
          : '';
        return '<div class="nb-session-card" data-session="' + esc(s.session_id) + '" '
          + 'style="background:var(--n-00,#fff);border:1px solid var(--bd-2,#e2e8f0);border-radius:14px;padding:14px 16px;margin-bottom:10px;cursor:pointer;transition:border-color .15s">'
          + '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px">'
          + '<div style="flex:1;min-width:0">'
          + protoBadge
          + (stepInfo ? '<span style="color:var(--n-500);font-size:12px;margin-left:8px">' + esc(stepInfo) + '</span>' : '')
          + '</div>'
          + '<div style="flex:0 0 auto;text-align:right">'
          + '<div style="font-size:11px;color:var(--n-400)">' + esc(fmtDate(s.last_at)) + '</div>'
          + '<div style="font-size:11px;color:var(--n-400)">' + esc(fmtClock(s.last_at)) + '</div>'
          + '</div>'
          + '</div>'
          + '<div style="display:flex;gap:16px;font-size:12px;color:var(--n-500)">'
          + '<span>' + s.record_count + ' 条记录</span>'
          + '<span>开始 ' + esc(fmtClock(s.first_at)) + '</span>'
          + '<span>最近 ' + esc(fmtClock(s.last_at)) + '</span>'
          + '</div>'
          + '</div>';
      }).join('');
      container.innerHTML = html;

      // 点击进入详情
      Array.prototype.forEach.call(container.querySelectorAll('.nb-session-card'), function (card) {
        card.onmouseenter = function () { this.style.borderColor = 'var(--brand,#3b67e8)'; };
        card.onmouseleave = function () { this.style.borderColor = 'var(--bd-2,#e2e8f0)'; };
        card.onclick = function () {
          notebookDetailSession = card.getAttribute('data-session');
          loadSessionDetail(notebookDetailSession);
        };
      });
    }).catch(function (err) {
      host.querySelector('#nb-list').innerHTML = '<div style="color:#c2410c;font-size:13px">读取实验本失败：' + esc(err.message || '') + '</div>';
    });
  }

  // ---------- 产物追踪渲染 ----------
  function renderProductsSection(container, chainData, sessionId) {
    var products = (chainData && chainData.products) || [];
    var consumes = (chainData && chainData.consumes) || [];

    function productCard(p) {
      var typeName = { sample: '样品', reagent: '试剂', culture: '培养物', tissue: '组织', cell: '细胞', dna: '核酸', protein: '蛋白', antibody: '抗体', other: '其他' }[p.product_type] || p.product_type;
      var storageBadge = p.storage_item_id
        ? '<span style="display:inline-block;background:#ede9fe;color:#7c3aed;padding:2px 7px;border-radius:5px;font-size:11px">已入库 #' + p.storage_item_id + '</span>'
        : '<span style="display:inline-block;background:#fef3c7;color:#92400e;padding:2px 7px;border-radius:5px;font-size:11px">未入库</span>';
      return '<div style="background:#fff;border:1px solid #e2e8f0;border-left:3px solid #7c3aed;border-radius:9px;padding:10px 12px;margin-bottom:8px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center">'
        + '<div><span style="font-weight:600;color:#0f172a">🔬 ' + esc(p.product_name) + '</span>'
        + '<span style="margin-left:8px;color:#64748b;font-size:12px">' + esc(typeName) + '</span></div>'
        + storageBadge
        + '</div>'
        + '<div style="font-size:12px;color:#64748b;margin-top:4px">'
        + (p.quantity ? esc(p.quantity) + ' ' + esc(p.unit || '') : '')
        + (p.notes ? ' · ' + esc(p.notes) : '')
        + ' · ' + esc(p.produced_at || '')
        + '</div></div>';
    }

    var productsHtml = products.length
      ? products.map(productCard).join('')
      : '<div style="color:#94a3b8;font-size:12px;padding:10px 0">还没有记录产物。做完实验后可以在这里记录产出了什么。</div>';

    var consumesHtml = '';
    if (consumes.length) {
      consumesHtml = '<div style="margin-top:14px"><div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:6px">📥 消耗的库存</div>'
        + consumes.map(function (c) {
          return '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:7px;padding:7px 9px;margin-bottom:5px;font-size:12px">'
            + esc(c.storage_name || '物品#' + c.storage_item_id)
            + (c.quantity_used ? ' · 用了 ' + esc(c.quantity_used) : '')
            + ' · ' + esc(c.consumed_at || '') + '</div>';
        }).join('') + '</div>';
    }

    // 添加产物表单
    var addFormHtml = '<div style="margin-top:14px;background:#f8fafc;border-radius:10px;padding:12px 14px">'
      + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:8px">📝 记录新产物（自动入库带溯源）</div>'
      + '<div style="display:flex;flex-wrap:wrap;gap:8px">'
      + '<input id="nb-prod-name" placeholder="产物名称（如：感受态细胞A1）" style="flex:1;min-width:160px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px">'
      + '<select id="nb-prod-type" style="padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px">'
      + '<option value="sample">样品</option><option value="reagent">试剂</option><option value="culture">培养物</option>'
      + '<option value="cell">细胞</option><option value="tissue">组织</option><option value="dna">核酸</option>'
      + '<option value="protein">蛋白</option><option value="antibody">抗体</option><option value="other">其他</option>'
      + '</select>'
      + '<input id="nb-prod-qty" placeholder="数量" style="width:70px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px">'
      + '<input id="nb-prod-unit" placeholder="单位" style="width:60px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px">'
      + '<input id="nb-prod-notes" placeholder="备注（保存条件等）" style="flex:1;min-width:120px;padding:7px 10px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px">'
      + '</div>'
      + '<div style="margin-top:8px;display:flex;gap:8px;align-items:center">'
      + '<label style="font-size:12px;color:#64748b"><input type="checkbox" id="nb-prod-tostorage" checked> 自动入库到储存库</label>'
      + '<button class="sh-btn primary" id="nb-prod-add" style="margin-left:auto;padding:5px 14px;font-size:12px">添加产物</button>'
      + '<span id="nb-prod-msg" style="font-size:12px;color:#64748b"></span>'
      + '</div></div>';

    container.innerHTML = '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:10px">🧬 实验产物</div>'
      + productsHtml + consumesHtml + addFormHtml;

    // 绑定添加产物按钮
    var addBtn = container.querySelector('#nb-prod-add');
    if (addBtn) addBtn.onclick = function () {
      var name = container.querySelector('#nb-prod-name').value.trim();
      if (!name) { container.querySelector('#nb-prod-msg').textContent = '请输入产物名称'; return; }
      var toStorage = container.querySelector('#nb-prod-tostorage').checked;
      addBtn.disabled = true;
      api('/planning/products', 'POST', {
        session_id: sessionId,
        product_name: name,
        product_type: container.querySelector('#nb-prod-type').value,
        quantity: container.querySelector('#nb-prod-qty').value.trim(),
        unit: container.querySelector('#nb-prod-unit').value.trim(),
        notes: container.querySelector('#nb-prod-notes').value.trim(),
        to_storage: toStorage,
      }).then(function (res) {
        if (res && res.detail) { container.querySelector('#nb-prod-msg').textContent = '失败：' + res.detail; addBtn.disabled = false; return; }
        container.querySelector('#nb-prod-msg').textContent = '已添加' + (res.storage_item_id ? ' 并入库 #' + res.storage_item_id : '');
        container.querySelector('#nb-prod-name').value = '';
        container.querySelector('#nb-prod-qty').value = '';
        container.querySelector('#nb-prod-notes').value = '';
        // 刷新产物列表
        api('/planning/chain/' + encodeURIComponent(sessionId)).then(function (chainData2) {
          renderProductsSection(container, chainData2, sessionId);
        });
      }).catch(function (e) {
        container.querySelector('#nb-prod-msg').textContent = '失败：' + e.message;
        addBtn.disabled = false;
      });
    };
  }

  function loadSessionDetail(sessionId) {
    var host = window.shellCanvas ? window.shellCanvas() : document.getElementById('sh-canvas');
    host.innerHTML = '<div style="max-width:880px;margin:0 auto;padding:8px 0">'
      + '<button class="sh-btn" id="nb-back" style="margin-bottom:14px">← 返回实验本</button>'
      + '<div id="nb-detail" style="color:var(--n-500)>正在加载…</div>'
      + '</div>';

    host.querySelector('#nb-back').onclick = function () {
      notebookDetailSession = null;
      loadSessionList();
    };

    api('/record/sessions/' + encodeURIComponent(sessionId)).then(function (data) {
      var d = host.querySelector('#nb-detail');
      var records = data.records || [];

      // 头部信息
      var header = '<div style="margin-bottom:20px">'
        + '<div style="font-size:18px;font-weight:700;color:var(--n-900,#0f172a)">' + esc(data.protocol_title || '自由实验') + '</div>'
        + '<div style="color:var(--n-500);font-size:12px;margin-top:4px">会话 ' + esc(sessionId.slice(0, 20)) + '… · ' + data.record_count + ' 条记录</div>'
        + '</div>';

      // 方案步骤进度
      var stepsHtml = '';
      if (data.steps && Object.keys(data.steps).length) {
        var stepNums = Object.keys(data.steps).sort(function (a, b) { return Number(a) - Number(b); });
        var currentStep = data.current_step_number;
        stepsHtml = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px">'
          + stepNums.map(function (n) {
            var isCur = Number(n) === Number(currentStep);
            var stepData = data.steps[n] || {};
            var hasValues = stepData.values && Object.keys(stepData.values).length;
            var bg = isCur ? 'var(--brand,#3b67e8)' : (hasValues ? 'var(--green-500,#16a34a)' : 'var(--n-100,#f1f5f9)');
            var color = (isCur || hasValues) ? '#fff' : 'var(--n-500)';
            return '<span style="display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;border-radius:6px;background:' + bg + ';color:' + color + ';font-size:11px;font-weight:600">'
              + esc(n) + '</span>';
          }).join('')
          + '</div>';
      }

      // 记录列表 — 复用 record_ledger_view 的 nb 样式
      var recordsHtml = '';
      if (records.length) {
        recordsHtml = records.map(function (item) {
          var entities = item.entities || {};
          var entityKeys = Object.keys(entities).filter(function (k) { return entities[k]; });
          var entityHtml = entityKeys.length
            ? '<div style="margin-top:8px">' + entityKeys.map(function (k) {
              return '<span style="display:inline-block;background:var(--brand-50,#eff6ff);color:#3730a3;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;font-size:11px">' + esc(k) + ' = ' + esc(entities[k]) + '</span>';
            }).join('') + '</div>'
            : '';
          var eval_ = item.evaluation || {};
          var devHtml = (eval_.deviations || []).map(function (dv) {
            return '<div style="background:#fff7ed;color:#c2410c;border-radius:7px;padding:7px 9px;margin-top:7px;font-size:12px">'
              + '<b>偏差：' + esc(dv.field || '') + '</b>'
              + '<div>期望：' + esc(dv.protocol_value || '') + ' · 实际：' + esc(dv.actual_value || '') + '</div></div>';
          }).join('');
          var step = item.step && item.step.step ? item.step.step.number : '';
          var transcript = item.transcript || '';
          // 计时结束的记录用不同样式
          var isTimer = transcript.indexOf('[计时结束]') === 0;
          var cardStyle = isTimer
            ? 'background:var(--amber-50,#fffbeb);border:1px solid var(--amber-200,#fde68a);border-left:3px solid var(--amber-500,#f59e0b)'
            : 'background:var(--n-00,#fff);border:1px solid var(--bd-2,#e2e8f0);border-left:3px solid var(--brand,#3b67e8)';
          return '<div style="' + cardStyle + ';border-radius:11px;padding:12px 14px;margin-bottom:9px">'
            + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px">'
            + '<span style="font-size:11px;color:var(--n-400)">'
            + (item.segment_id ? '第 ' + item.segment_id + ' 段' : '')
            + (step ? ' · 步骤 ' + step : '')
            + '</span>'
            + '<span style="font-size:11px;color:var(--n-400)">' + esc(fmtClock(item.at)) + '</span>'
            + '</div>'
            + '<div style="color:var(--n-800,#334155);line-height:1.7;font-size:13px">' + esc(transcript) + '</div>'
            + entityHtml + devHtml
            + '</div>';
        }).join('');
      } else {
        recordsHtml = '<div style="color:var(--n-500);font-size:13px;padding:30px;text-align:center">该会话还没有记录。</div>';
      }

      d.innerHTML = header + stepsHtml + recordsHtml;

      // 产物追踪区
      var productsSection = '<div id="nb-products-section" style="margin-top:20px;padding-top:16px;border-top:2px solid var(--bd-2,#e2e8f0)">加载产物信息…</div>';
      d.insertAdjacentHTML('beforeend', productsSection);

      // 加载产物数据
      api('/planning/chain/' + encodeURIComponent(sessionId)).then(function (chainData) {
        var ps = d.querySelector('#nb-products-section');
        renderProductsSection(ps, chainData, sessionId);
      }).catch(function () {
        var ps = d.querySelector('#nb-products-section');
        if (ps) ps.innerHTML = '';
      });
    }).catch(function (err) {
      host.querySelector('#nb-detail').innerHTML = '<div style="color:#c2410c;font-size:13px">加载失败：' + esc(err.message || '') + '</div>';
    });
  }

  window.labRecordsReload = reloadRecords;
  window.shellRegisterView('records', reloadRecords);

  // ---------- 设置页：分类侧边栏 + 内容区 ----------
  window.shellRegisterView('settings', function (host) {
    var categories = [
      { id: 'model', label: '文本模型' },
      { id: 'personal', label: '个人中心' },
      { id: 'voice', label: '语音模型' },
      { id: 'doc', label: '文档解析' },
      { id: 'experiment', label: '实验与数据' },
      { id: 'conversation', label: '会话' },
      { id: 'appearance', label: '外观与形象' },
      { id: 'proxy', label: '代理与网络' },
      { id: 'system', label: '系统环境' },
      { id: 'about', label: '关于' }
    ];
    var categoryDescriptions = {
      'model': '负责文字对话/思考的模型提供方',
      'personal': '账号、安全、数据统计、个性化设置',
      'voice': '语音合成 TTS、实时语音 QwenAudio、语音策略',
      'doc': 'PDF/MinerU、图片 OCR 等文档解析',
      'experiment': '方案库、试剂配置库、危化品库、实验记录',
      'conversation': '会话标题、历史保留、自动创建',
      'appearance': '形象帧、口型动画、眼神跟随、主题',
      'proxy': '访问外网与科大接口的代理配置',
      'system': '数据目录、日志目录、模型缓存目录',
      'about': '版本、仓库、团队开发标准'
    };
    host.innerHTML = '<div style="display:flex;max-width:1180px;min-height:calc(100vh - 80px);gap:18px;margin:0 auto">'
      + '<div style="width:190px;flex:0 0 190px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:10px;height:max-content">'
      + categories.map(function (c) {
          return '<div class="settings-nav" data-pane="' + c.id + '" style="padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px;color:#334155;margin-bottom:2px">' + esc(c.label) + '</div>';
        }).join('')
      + '</div>'
      + '<div style="flex:1;min-width:0;position:relative" id="settings-body">'
      + '<div id="settings-pane"></div>'
      + '<div id="settings-inline-holder" style="display:none;position:absolute;inset:0"></div>'
      + '</div></div>'

    var pane = host.querySelector('#settings-pane');
    window.__settingsCleanup = function () {
      var holder = document.getElementById('settings-inline-holder');
      var modal = document.getElementById('settings-modal');
      if (holder && holder.firstElementChild && modal) modal.appendChild(holder.firstElementChild);
    };
    function showPane(id) {
      Array.prototype.forEach.call(host.querySelectorAll('.settings-nav'), function (nav) {
        nav.style.background = nav.dataset.pane === id ? '#eff6ff' : '';
        nav.style.color = nav.dataset.pane === id ? '#1d4ed8' : '#334155';
        nav.style.fontWeight = nav.dataset.pane === id ? '600' : '400';
      });
      var holder = document.getElementById('settings-inline-holder');
      var modal = document.getElementById('settings-modal');
      if (holder && holder.firstElementChild && modal) {
        modal.appendChild(holder.firstElementChild);
        holder.style.display = 'none';
      }
      if (holder) holder.style.display = 'none';
      function showLegacySection(sectionId) {
        var legacySettingsBox = document.querySelector('#settings-modal .settings-box');
        var inlineHolder = document.getElementById('settings-inline-holder');
        if (!legacySettingsBox || !inlineHolder) return false;
        pane.style.display = 'none';
        if (legacySettingsBox.parentElement !== inlineHolder) {
          inlineHolder.appendChild(legacySettingsBox);
        }
        inlineHolder.style.display = 'block';
        var legacyClose = legacySettingsBox.querySelector('#settings-close');
        if (legacyClose) legacyClose.style.display = 'none';
        Array.prototype.forEach.call(
          legacySettingsBox.querySelectorAll('.settings-section'),
          function (section) {
            section.style.display = section.dataset.section === sectionId ? 'block' : 'none';
          }
        );
        var legacyStatus = legacySettingsBox.querySelector('#settings-status');
        if (legacyStatus) {
          fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
            legacyStatus.className = 'settings-status ' + (d.ready ? 'ok' : 'warn');
            legacyStatus.textContent = d.ready ? '模型已配置，可以正常对话。' : ((d.missing || []).join('；') || '尚未完成配置') + '。填写后即可使用。';
          }).catch(function () {});
        }
        return true;
      }
      if (id === 'personal') {
        pane.style.display = '';
        if (window.renderPersonalCenter) {
          window.renderPersonalCenter(pane);
        } else {
          pane.innerHTML = '<div style="color:#64748b;padding:30px">个人中心加载中…</div>';
        }
        return;
      }
      if (id === 'voice' || id === 'doc') {
        if (showLegacySection(id)) return;
        pane.style.display = '';
        pane.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px 30px;max-width:760px">'
          + '<div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:10px">' + esc(categories.filter(function (c) { return c.id === id; })[0].label) + '</div>'
          + '<div style="color:#64748b;font-size:13px;line-height:1.8">' + esc(categoryDescriptions[id] || '') + '</div>'
          + '<div style="margin-top:14px;padding:12px 14px;background:#f8fafc;border:1px dashed #e2e8f0;border-radius:10px;color:#94a3b8;font-size:12px">该分类的设置项会随后台配置一起完善。</div></div>';
        return;
      }
      if (id === 'model') {
        pane.style.display = '';
        pane.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px 30px;max-width:920px">'
          + '<div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:16px">自定义模型</div>'
          + '<div style="background:#f8fafc;border:1px solid #eef2f7;border-radius:14px;padding:16px 20px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap">'
          + '<div><div style="font-weight:600;color:#0f172a;margin-bottom:3px">本地配置文件</div>'
          + '<div style="color:#64748b;font-size:12px;line-height:1.7">管理写入到 <code style="background:#eef2f7;padding:1px 5px;border-radius:5px">web/settings.json</code> 的本地自定义模型配置。</div></div>'
          + '<button class="sh-btn primary" id="model-add-provider" type="button">＋ 添加模型</button>'
          + '</div>'
          + '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin:22px 0 10px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">已保存模型</div>'
          + '<div style="display:flex;gap:8px"><button class="sh-btn" id="model-test-current" type="button">测试当前模型</button>'
          + '<button class="sh-btn" id="model-refresh" type="button">刷新列表</button></div>'
          + '</div>'
          + '<div id="model-provider-list"></div>'
          + '<div id="model-test-result" style="margin-top:8px;font-size:12px;color:#64748b"></div>'
          + '<div id="model-editor-holder" style="margin-top:14px;display:none"></div>'
          + '</div>';
        var listHost = pane.querySelector('#model-provider-list');
        var editorHolder = pane.querySelector('#model-editor-holder');

        function loadProviders() {
          listHost.innerHTML = '<div style="color:#94a3b8;font-size:13px">正在加载供应商…</div>';
          return api('/settings/providers').then(function (data) {
            var items = data.items || [];
            var currentReady = data.settings && data.settings.ready;
            var thinkSelect = document.getElementById('model-thinking-level');
            if (thinkSelect && data.settings && data.settings.thinking_level) {
              thinkSelect.value = data.settings.thinking_level;
              if (!thinkSelect.onchange) {
                thinkSelect.onchange = function () {
                  api('/settings', 'PUT', { thinking_level: thinkSelect.value }).then(function () {
                    loadProviders();
                  });
                };
              }
            }
            listHost.innerHTML = items.map(function (p) {
              var active = p.active ? '<span style="background:#eff6ff;color:#2563eb;padding:2px 8px;border-radius:999px;font-size:11px">当前</span>' : '';
              var tag = (p.kind === 'custom' ? '自定义' : p.label);
              var keyDot = p.key_set ? '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#22c55e;margin-left:6px" title="已配置密钥"></span>' : '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#cbd5e1;margin-left:6px" title="未配置密钥"></span>';
              var actions = '<button class="sh-btn" data-edit="' + p.id + '" type="button" title="编辑" style="padding:5px 9px">✎</button> '
                + (p.kind === 'custom' || p.id === 'custom' ? '<button class="sh-btn" data-del="' + p.id + '" type="button" title="删除" style="padding:5px 9px;color:#dc2626">🗑</button>' : '');
              var switchHint = p.active ? '' : (p.key_set ? '<div style="color:#94a3b8;font-size:11px;margin-top:2px">点击此行切换使用</div>' : '');
              return '<div style="display:flex;align-items:center;gap:12px;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;margin-bottom:8px;background:#fff;cursor:pointer" data-row="' + p.id + '">'
                + '<div style="width:34px;height:34px;flex:0 0 34px;border-radius:10px;background:#f1f5f9;display:flex;align-items:center;justify-content:center;color:#475569;font-size:16px">⊕</div>'
                + '<div style="flex:1;min-width:0"><div style="font-weight:600;color:#0f172a">' + esc(p.model) + '</div>'
                + '<div style="color:#64748b;font-size:12px;margin-top:2px">' + esc(tag) + keyDot + ' ' + active + '</div>'
                + '<div style="color:#94a3b8;font-size:11px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(p.base_url || '—') + '</div>'
                + switchHint + '</div>'
                + '<div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">' + actions + '</div></div>';
            }).join('') || '<div style="color:#64748b;font-size:13px">还没有已保存的模型。</div>';
            Array.prototype.forEach.call(listHost.querySelectorAll('[data-edit]'), function (btn) {
              btn.onclick = function () {
                var p = items.filter(function (x) { return x.id === btn.dataset.edit; })[0];
                openEditor(p);
              };
            });
            Array.prototype.forEach.call(listHost.querySelectorAll('[data-test]'), function (btn) {
              btn.onclick = function (e) {
                e.stopPropagation();
                var p = items.filter(function (x) { return x.id === btn.dataset.test; })[0];
                if (!p) return;
                var resultBox = document.getElementById('model-test-result');
                if (resultBox) resultBox.textContent = '正在测试 ' + p.label + '…';
                fetch('/settings/test', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ provider_id: p.id, base_url: p.base_url, model_name: p.model })
                }).then(function (r) { return r.json().catch(function () { return { ok: false, message: '请求失败' }; }); })
                  .then(function (d) {
                    if (resultBox) {
                      resultBox.textContent = d.ok ? ('✅ ' + p.label + ' 连接成功') : ('❌ ' + p.label + '：' + (d.message || d.detail || '失败'));
                      resultBox.style.color = d.ok ? '#047857' : '#dc2626';
                    }
                  }).catch(function (err) {
                    if (resultBox) { resultBox.textContent = '测试失败：' + String(err); resultBox.style.color = '#dc2626'; }
                  });
              };
            });
            Array.prototype.forEach.call(listHost.querySelectorAll('[data-activate]'), function (btn) {
              btn.onclick = function () {
                var p = items.filter(function (x) { return x.id === btn.dataset.activate; })[0];
                if (!p) return;
                api('/settings', 'PUT', {
                  provider_id: p.id,
                  provider_label: p.label || p.id,
                  base_url: p.base_url,
                  model_name: p.model,
                  thinking_level: (document.getElementById('model-thinking-level') || {}).value
                }).then(function () {
                  loadProviders();
                }).catch(function (e) {
                  listHost.insertAdjacentHTML('afterend', '<div style="color:#dc2626;font-size:12px;padding:6px 2px">切换失败：' + esc(e.detail || e.message || e) + '</div>');
                });
              };
            });
            Array.prototype.forEach.call(listHost.querySelectorAll('[data-row]'), function (row) {
              row.onclick = function () {
                var p = items.filter(function (x) { return x.id === row.dataset.row; })[0];
                if (!p || p.active || !p.key_set) return;
                api('/settings', 'PUT', {
                  provider_id: p.id,
                  provider_label: p.label || p.id,
                  base_url: p.base_url,
                  model_name: p.model
                }).then(function () {
                  loadProviders();
                }).catch(function () {});
              };
            });
            Array.prototype.forEach.call(listHost.querySelectorAll('[data-del]'), function (btn) {
              btn.onclick = function () {
                if (!confirm('确定删除该自定义提供方？')) return;
                api('/settings/providers/' + btn.dataset.del, 'DELETE').then(loadProviders);
              };
            });
          }).catch(function (e) {
            listHost.innerHTML = '<div style="color:#c2410c;font-size:13px">读取失败：' + esc(e.message || e) + '</div>';
          });
        }

        function openEditor(provider) {
          editorHolder.style.display = 'block';
          if (provider) {
            var row = listHost.querySelector('[data-row="' + provider.id + '"]');
            if (row && row.parentNode) {
              row.parentNode.insertBefore(editorHolder, row.nextSibling);
            }
          }
          var customId = provider && provider.kind === 'custom' ? provider.id : '';
          var isCustom = provider && provider.kind === 'custom';
          var title = provider ? (provider.label || provider.id) : '添加模型';
          editorHolder.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:22px 24px;box-shadow:0 6px 18px rgba(15,23,42,.04)">'
            + '<div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:16px">' + esc(title) + '</div>'
            + (provider ? '' : '<label style="display:block;margin-bottom:12px;font-size:12px;color:#475569">提供方'
              + '<select id="provider-select" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#0f172a"></select></label>'
              + '<label id="provider-id-field" style="display:none;margin-bottom:12px;font-size:12px;color:#475569">提供方 ID'
              + '<input id="provider-id" type="text" placeholder="例如 my-provider" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px"></label>')
            + '<label style="display:block;margin-bottom:16px;font-size:12px;color:#475569">API 密钥'
            + '<input id="provider-key" type="password" autocomplete="new-password" placeholder="已配置——输入新值可替换" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:10px 12px;border:1px solid #e2e8f0;border-radius:10px"></label>'
            + '<details open style="margin-bottom:16px"><summary style="cursor:pointer;font-size:13px;font-weight:600;color:#334155">自定义设置</summary>'
            + '<div style="padding:12px 0 0">'
            + '<label style="display:block;margin-bottom:12px;font-size:12px;color:#475569">显示名称'
            + '<input id="provider-label" type="text" value="' + esc(provider ? provider.label : '') + '" placeholder="例如 keda" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:9px 11px;border:1px solid #e2e8f0;border-radius:10px"></label>'
            + '<label style="display:block;margin-bottom:12px;font-size:12px;color:#475569">API 地址'
            + '<input id="provider-base-url" type="text" value="' + esc(provider ? provider.base_url : '') + '" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:9px 11px;border:1px solid #e2e8f0;border-radius:10px"></label>'
            + '<label style="display:block;margin-bottom:4px;font-size:12px;color:#475569">API 协议'
            + '<select id="provider-protocol" style="display:block;width:100%;box-sizing:border-box;margin-top:4px;padding:9px 11px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;color:#0f172a">'
            + '<option value="openai-completions">openai-completions</option>'
            + '<option value="openai-responses">openai-responses</option>'
            + '<option value="anthropic-messages">anthropic-messages</option>'
            + '</select></label>'
            + '</div></details>'
            + '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid #eef2f7;padding-top:14px">'
            + '<div><div style="font-size:13px;font-weight:700;color:#0f172a">模型目录</div>'
            + '<div style="font-size:12px;color:#64748b;margin-top:2px">已自定义模型目录</div></div>'
            + '<div style="display:flex;gap:8px">'
            + '<button class="sh-btn" id="provider-reset-models" type="button">恢复默认模型</button>'
            + '<button class="sh-btn" id="provider-fetch" type="button">获取可用模型</button>'
            + '</div></div>'
            + '<div style="display:flex;gap:8px;align-items:center;border:1px solid #e2e8f0;border-radius:10px;padding:8px 10px;margin-top:10px">'
            + '<input id="provider-model" type="text" value="' + esc(provider ? provider.model : '') + '" placeholder="模型 ID" style="flex:1;min-width:120px;padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px">'
            + '<input id="provider-model-label" type="text" placeholder="显示名称" style="flex:1;min-width:120px;padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px">'
            + '<button class="sh-btn" id="provider-model-delete" type="button" title="删除" style="padding:5px 9px;color:#dc2626">🗑</button>'
            + '</div>'
            + '<select id="provider-model-select" style="display:none;width:100%;box-sizing:border-box;margin:10px 0;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#0f172a;font-size:13px"></select>'
            + '<div style="display:flex;gap:10px;margin-top:16px"><button class="sh-btn primary" id="provider-save" type="button">保存</button>'
            + '<button class="sh-btn" id="provider-cancel" type="button">取消</button></div>'
            + '<div id="provider-msg" style="margin-top:10px;font-size:12px;color:#64748b"></div>'
            + '</div>';
          var select = editorHolder.querySelector('#provider-select');
          var idField = editorHolder.querySelector('#provider-id-field');
          var idInput = editorHolder.querySelector('#provider-id');
          var labelInput = editorHolder.querySelector('#provider-label');
          var baseInput = editorHolder.querySelector('#provider-base-url');
          var modelInput = editorHolder.querySelector('#provider-model');
          var modelLabelInput = editorHolder.querySelector('#provider-model-label');
          var protocolSelect = editorHolder.querySelector('#provider-protocol');
          var modelSelect = editorHolder.querySelector('#provider-model-select');
          var keyInput = editorHolder.querySelector('#provider-key');
          var msg = editorHolder.querySelector('#provider-msg');
          if (keyInput) keyInput.value = '';

          function setCustomVisible(show) { if (idField) idField.style.display = show ? 'block' : 'none'; }
          if (idField) setCustomVisible(Boolean(!provider && isCustom));
          if (idInput && provider && provider.kind === 'custom') {
            idInput.value = provider.id;
          }
          if (select) {
            if (isCustom) {
              select.value = '__custom__';
            }
            api('/settings/providers').then(function (data) {
              var opts = data.items || [];
              var builtin = opts.filter(function (x) { return x.kind === 'preset'; });
              builtin.forEach(function (p) {
                var o = document.createElement('option');
                o.value = p.id;
                o.textContent = p.label;
                if (provider && provider.id === p.id) o.selected = true;
                select.appendChild(o);
              });
            });
            select.onchange = function () {
              var val = select.value;
              if (val === '__custom__') {
                setCustomVisible(true);
                if (idInput && !idInput.value) idInput.value = 'provider-' + Date.now().toString(36);
                return;
              }
              setCustomVisible(false);
              fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
                var preset = (d.presets || []).filter(function (x) { return x.id === val; })[0];
                if (preset) { baseInput.value = preset.base_url; modelInput.value = preset.model; }
              });
            };
          }

          editorHolder.querySelector('#provider-fetch').onclick = function () {
            msg.textContent = '正在拉取模型…';
            modelSelect.style.display = 'none';
            var providerId = provider ? provider.id : (select ? select.value : '');
            // 用户刚在输入框里填了 Key 就优先用它拉取，不需要先保存；
            // 没填时才回退到后端已保存的 Key。
            var fetchPayload = {
              base_url: baseInput.value.trim(),
              provider_id: providerId,
              api_key: keyInput.value.trim()
            };
            fetch('/settings/models', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify(fetchPayload)
            }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
              .then(function (res) {
                if (!res.ok) {
                  msg.textContent = res.d.detail || '拉取失败';
                  return;
                }
                var list = (res.d.models || []).filter(function (m) {
                  return m && ['mineru', 'unlimited-ocr', 'qwen3-embedding', 'qwen3-reranker'].indexOf(m) < 0;
                });
                modelSelect.innerHTML = '<option value="">请选择模型…</option>' + list.map(function (m) {
                  return '<option value="' + m + '">' + m + '</option>';
                }).join('');
                modelSelect.style.display = list.length ? 'block' : 'none';
                msg.textContent = list.length ? ('拉到 ' + list.length + ' 个模型，请从下拉框选择。') : '没有拉到模型。';
              })
              .catch(function (e) { msg.textContent = '拉取失败：' + String(e); });
          };
          modelSelect.onchange = function () {
            if (modelSelect.value) modelInput.value = modelSelect.value;
          };

          var resetModelsBtn = editorHolder.querySelector('#provider-reset-models');
          if (resetModelsBtn) resetModelsBtn.onclick = function () {
            var val = select ? select.value : (provider ? provider.id : '');
            if (!val || val === '__custom__') {
              msg.textContent = '当前没有可恢复的内置默认模型。';
              return;
            }
            fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
              var preset = (d.presets || []).filter(function (x) { return x.id === val; })[0];
              if (preset) { baseInput.value = preset.base_url; modelInput.value = preset.model; msg.textContent = '已恢复默认模型：' + preset.model; }
            });
          };

          editorHolder.querySelector('#provider-save').onclick = function () {
            var isCustomSave = Boolean(provider && provider.kind === 'custom') || (!provider && select && select.value === '__custom__');
            var pickedId;
            if (provider) {
              pickedId = provider.id;
            } else if (isCustomSave) {
              pickedId = idInput ? idInput.value.trim() : '';
            } else {
              pickedId = select ? select.value : '';
            }
            if (!pickedId) { msg.textContent = '请选择或填写提供方 ID'; return; }
            var label = (labelInput && labelInput.value.trim()) || (provider ? provider.label : '') || pickedId;
            var payload = {
              provider_id: pickedId,
              label: label,
              base_url: baseInput.value.trim(),
              model: modelInput.value.trim()
            };
            if (keyInput.value.trim()) payload.api_key = keyInput.value.trim();
            var request;
            if (isCustomSave) {
              request = api('/settings/providers', 'POST', payload);
            } else {
              request = api('/settings', 'PUT', {
                provider_id: pickedId,
                provider_label: label,
                base_url: baseInput.value.trim(),
                model_name: modelInput.value.trim(),
                api_key: keyInput.value.trim() || undefined
              });
            }
            request.then(function (res) {
              msg.textContent = '已保存';
              editorHolder.style.display = 'none';
              loadProviders();
            }).catch(function (e) {
              msg.textContent = String(e.detail || e.message || e);
            });
          };
          var deleteModelBtn = editorHolder.querySelector('#provider-model-delete');
          if (deleteModelBtn) deleteModelBtn.onclick = function () {
            modelInput.value = '';
            modelLabelInput.value = '';
            msg.textContent = '已清空模型，请重新选择。';
          };

          editorHolder.querySelector('#provider-cancel').onclick = function () {
            editorHolder.style.display = 'none';
          };
        }

        pane.querySelector('#model-add-provider').onclick = function () { openEditor(null); };
        pane.querySelector('#model-refresh').onclick = loadProviders;
        pane.querySelector('#model-test-current').onclick = function () {
          var resultBox = document.getElementById('model-test-result');
          if (resultBox) { resultBox.textContent = '正在测试当前模型…'; resultBox.style.color = '#64748b'; }
          fetch('/settings/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}'
          }).then(function (r) { return r.json().catch(function () { return { ok: false, message: '请求失败' }; }); })
            .then(function (d) {
              if (resultBox) {
                resultBox.textContent = d.ok ? '✅ 当前模型连接成功' : ('❌ ' + (d.message || d.detail || '失败'));
                resultBox.style.color = d.ok ? '#047857' : '#dc2626';
              }
            }).catch(function (e) {
              if (resultBox) { resultBox.textContent = '测试失败：' + String(e); resultBox.style.color = '#dc2626'; }
            });
        };
        loadProviders();

        var dashKeyInput = pane.querySelector('#settings-view-dashscope-key');
        var dashStatus = pane.querySelector('#settings-view-dashscope-status');
        function dashStatusText(html, color) {
          dashStatus.innerHTML = html;
          dashStatus.style.color = color || '#64748b';
        }
        function refreshDashStatus() {
          dashStatusText('正在检测实时语音服务…', '#64748b');
          return fetch('/settings/qwen-audio', { cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (d.ok) {
                dashStatusText('✅ 运行中：' + d.url, '#047857');
              } else if (d.dashscope_key_set) {
                dashStatusText('服务未运行，点“保存 Key 并启动实时语音”。', '#b45309');
              } else {
                dashStatusText('尚未填写 DashScope Key，请在上方获取并粘贴。', '#b45309');
              }
            })
            .catch(function () { dashStatusText('状态查询失败', '#dc2626'); });
        }
        pane.querySelector('#settings-view-dashscope-refresh').onclick = refreshDashStatus;
        pane.querySelector('#settings-view-dashscope-save').onclick = function () {
          var btn = pane.querySelector('#settings-view-dashscope-save');
          var key = (dashKeyInput.value || '').trim();
          var step = function () {
            return fetch('/settings/qwen-audio/start', { method: 'POST' })
              .then(function (r) { return r.json(); })
              .then(function (d) {
                dashStatusText(d.message || (d.ok ? '已启动' : '启动失败'), d.ok ? '#047857' : '#dc2626');
                btn.disabled = false;
                return d;
              })
              .catch(function (e) {
                btn.disabled = false;
                dashStatusText('启动请求失败：' + String(e), '#dc2626');
              });
          };
          btn.disabled = true;
          dashStatusText('正在保存并启动…', '#64748b');
          var save = Promise.resolve();
          if (key) {
            save = fetch('/settings', {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ dashscope_api_key: key })
            }).then(function (r) {
              if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || '保存失败'); });
              return r.json();
            }).then(function () { dashKeyInput.value = ''; });
          }
          save.then(step).catch(function (e) {
            btn.disabled = false;
            dashStatusText('保存失败：' + String(e.message || e), '#dc2626');
          });
        };
        refreshDashStatus();
        return;
      }
      pane.style.display = '';
      if (id === 'appearance') {
        var avatarOn = localStorage.getItem('lab-avatar-enabled') !== '0';
        var avatarSize = parseInt(localStorage.getItem('lab-avatar-size'), 10) || 225;
        pane.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px 30px;max-width:760px">'
          + '<div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:10px">外观与形象</div>'
          + '<div style="color:#64748b;font-size:13px;line-height:1.8;margin-bottom:18px">小科形象显示开关与大小。设置会保存在当前浏览器。</div>'
          + '<div style="display:flex;flex-direction:column;gap:18px">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px">'
          + '<div><div style="font-weight:600;color:#0f172a">显示小科形象</div><div style="color:#64748b;font-size:12px;margin-top:3px">关闭后实验进行中也不会显示</div></div>'
          + '<input type="checkbox" id="avatar-enabled" ' + (avatarOn ? 'checked' : '') + ' style="width:20px;height:20px;accent-color:#2563eb"></div>'
          + '<div style="border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px">'
          + '<div style="display:flex;justify-content:space-between;align-items:center"><div style="font-weight:600;color:#0f172a">形象大小</div><span id="avatar-size-label" style="font-size:13px;color:#2563eb;font-weight:600">' + avatarSize + 'px</span></div>'
          + '<input type="range" id="avatar-size" min="120" max="360" step="10" value="' + avatarSize + '" style="width:100%;margin-top:10px">'
          + '<div style="display:flex;justify-content:space-between;color:#94a3b8;font-size:11px;margin-top:2px"><span>小 120px</span><span>默认 225px</span><span>大 360px</span></div></div>'
          + '<div style="display:flex;justify-content:flex-end;gap:10px"><button class="sh-btn primary" id="avatar-save">保存</button></div>'
          + '</div></div>';
        var enabledInput = pane.querySelector('#avatar-enabled');
        var sizeInput = pane.querySelector('#avatar-size');
        var sizeLabel = pane.querySelector('#avatar-size-label');
        pane.querySelector('#avatar-save').onclick = function () {
          var enabled = enabledInput.checked;
          var size = parseInt(sizeInput.value, 10) || 225;
          if (typeof window.applyAvatarSettings === 'function') window.applyAvatarSettings(enabled, size, true);
          var msg = sizeLabel;
          msg.textContent = '已保存';
          setTimeout(function () { msg.textContent = size + 'px'; }, 1200);
        };
        enabledInput.onchange = function () {
          if (typeof window.applyAvatarSettings === 'function') window.applyAvatarSettings(enabledInput.checked, parseInt(sizeInput.value, 10) || 225, true);
        };
        sizeInput.oninput = function () { sizeLabel.textContent = sizeInput.value + 'px'; };
        return;
      }
      pane.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px 30px;max-width:760px">'
        + '<div style="font-size:17px;font-weight:700;color:#0f172a;margin-bottom:10px">' + esc(categories.filter(function (c) { return c.id === id; })[0].label) + '</div>'
        + '<div style="color:#64748b;font-size:13px;line-height:1.8">' + esc(categoryDescriptions[id] || '') + '</div>'
        + '<div style="margin-top:14px;padding:12px 14px;background:#f8fafc;border:1px dashed #e2e8f0;border-radius:10px;color:#94a3b8;font-size:12px">该分类的设置项会根据项目需要逐步加入。</div></div>';
    }
    Array.prototype.forEach.call(host.querySelectorAll('.settings-nav'), function (nav) {
      nav.onclick = function () { showPane(nav.dataset.pane); };
    });
    showPane('model');
  });

  document.addEventListener('shell-ready', function () {
    refreshStatus();
    setInterval(refreshStatus, 5000);
  });
})();
