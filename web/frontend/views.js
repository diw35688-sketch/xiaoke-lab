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
      bits.push(p.mode === 'protocol'
        ? '<span class="sh-pill">' + esc(p.protocol.title) + ' · 第 ' + p.step.number + '/' + p.protocol.total_steps + ' 步</span>'
        : '<span class="sh-pill">自由记录模式</span>');
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

  // ---------- 实验方案页 ----------
  window.shellRegisterView('protocols', function (host) {
    api('/protocols').then(function (d) {
      ensureCardStyles();
      var protocolPageSize = 6;
      function protocolMark(text, q) {
        var safe = esc(text);
        if (!q) return safe;
        var escaped = String(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return safe.replace(new RegExp('(' + escaped + ')', 'gi'), '<mark>$1</mark>');
      }
      function startProtocol(id) {
        api('/protocols/session', 'POST', { protocol_id: id || null }).then(function () {
          window.interactionModeState.select(id ? 'protocol' : 'free', id || null);
          refreshStatus();
          window.shellShow('chat');
          if (window.composerRefresh) window.composerRefresh();
          if (window.labStepsReload) window.labStepsReload();
        });
      }
      host.innerHTML = '<div class="card-toolbar">'
        + '<input type="search" id="protocol-search" placeholder="搜索方案名称 / 来源…" autocomplete="off">'
        + '<button class="sh-btn primary" id="protocol-chat-create">AI 创建</button>'
        + '<button class="sh-btn" id="protocol-file-btn">选择文件</button>'
        + '<input type="file" id="protocol-file" accept=".json,.pdf,.png,.jpg,.jpeg" style="display:none">'
        + '<span id="protocol-file-msg" style="font-size:12px;color:#64748b"></span>'
        + '</div>'
        + '<div class="search-note">文件自动识别：JSON 直接入库；PDF/图片走 OCR 识别成方案</div>'
        + '<div id="protocol-summary" style="font-size:12px;color:#64748b;margin:2px 0 10px"></div>'
        + '<div id="protocol-grid" class="card-grid"></div>'
        + '<div id="protocol-more-box" style="margin-top:10px;text-align:center"></div>'
        + '<div id="ai-draft-box"></div>'
        + '<div id="ocr-draft-box"></div>';

      function renderProtocols(items, all, q) {
        var visible = items.slice(0, protocolPageSize);
        var cards = visible.map(function (p) {
          var on = session && session.mode === 'protocol' && session.protocol.id === p.id;
          return '<div class="p-card' + (on ? ' active' : '') + '" data-id="' + p.id + '">'
            + '<div style="font-weight:600;color:#0f172a;margin-bottom:5px">' + protocolMark(p.title, q)
            + (on ? '<span style="color:#2563eb;font-size:12px;margin-left:8px">进行中</span>' : '') + '</div>'
            + '<div style="color:#64748b;font-size:12px;line-height:1.6">共 ' + p.total_steps + ' 步 · ' + protocolMark(p.source, q) + '</div>'
            + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-view-detail="' + p.id + '" style="padding:3px 9px;font-size:12px">查看方案</button></div></div>';
        }).join('');
        var freeActive = session && session.mode === 'free';
        var grid = host.querySelector('#protocol-grid');
        grid.innerHTML = '<div class="p-card' + (freeActive ? ' active' : '') + '" data-id="">'
          + '<div style="font-weight:600;color:#0f172a">自由记录模式</div>'
          + '<div style="color:#64748b;font-size:12px;margin-top:4px">不按方案，只做记录，不产生方案性追问</div>'
          + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-view-detail="" style="padding:3px 9px;font-size:12px">进入</button></div></div>'
          + cards || '<div class="card-empty">没有匹配的方案。</div>';
        Array.prototype.forEach.call(grid.querySelectorAll('.p-card'), function (card) {
          card.onclick = function (e) {
            if (e.target.closest('[data-view-detail]')) return;
            startProtocol(card.dataset.id);
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-view-detail]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-view-detail');
            if (!id) {
              startProtocol('');
              return;
            }
            showProtocolDetail(host, id);
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
      protocolPageSize = 6;
      renderProtocols(d.protocols || [], d.protocols || [], '');
      var searchInput = host.querySelector('#protocol-search');
      searchInput.addEventListener('input', function () {
        var q = searchInput.value.trim().toLowerCase();
        protocolPageSize = 6;
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
          fetch('/protocols/upload-file', { method: 'POST', body: form }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
          }).then(function (res) {
            if (!res.ok) { msg.textContent = res.d.detail || '识别失败'; return; }
            var drafts = res.d.drafts || [];
            msg.textContent = '识别出 ' + drafts.length + ' 个实验，请逐个确认保存';
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

      Array.prototype.forEach.call(host.querySelectorAll('.p-card'), function (card) {
        card.onclick = function () {
          api('/protocols/session', 'POST', { protocol_id: card.dataset.id || null }).then(function () {
            window.interactionModeState.select(card.dataset.id ? 'protocol' : 'free', card.dataset.id || null);
            refreshStatus();
            window.shellShow('chat');
            if (window.composerRefresh) window.composerRefresh();
            if (window.labStepsReload) window.labStepsReload();
          });
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
            + '<div style="margin-bottom:14px"><button class="sh-btn primary" id="protocol-select-detail">选择此方案开始实验</button>'
            + '<button class="sh-btn" id="protocol-edit-detail" style="margin-left:8px">编辑当前步骤</button></div>'
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
          host.querySelector('#protocol-select-detail').onclick = function () {
            api('/protocols/session', 'POST', { protocol_id: protocolId }).then(function () {
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

  // ---------- 本次记录页 ----------
  function reloadRecords() {
    var host = window.shellCanvas ? window.shellCanvas() : document.getElementById('sh-canvas');
    if (!host) return;
    var path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/record/history')
      : '/record/history';
    api(path).then(function (data) {
      host.innerHTML = window.renderExperimentLedger(data);
    }).catch(function (error) {
      host.innerHTML = '<div style="color:#c2410c;font-size:13px">读取本次实验账本失败：'
        + esc(error.message || '未知错误') + '</div>';
    });
  }
  window.labRecordsReload = reloadRecords;
  window.shellRegisterView('records', reloadRecords);

  // ---------- 设置页：分类侧边栏 + 内容区 ----------
  window.shellRegisterView('settings', function (host) {
    var categories = [
      { id: 'model', label: '模型与语音' },
      { id: 'experiment', label: '实验与数据' },
      { id: 'conversation', label: '会话' },
      { id: 'appearance', label: '外观与形象' },
      { id: 'proxy', label: '代理与网络' },
      { id: 'system', label: '系统环境' },
      { id: 'about', label: '关于' }
    ];
    var categoryDescriptions = {
      'model': '文字模型、文档解析 MinerU/OCR、语音合成',
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
      if (id === 'model') {
        pane.innerHTML = '';
        pane.style.display = 'none';
        var modal = document.getElementById('settings-modal');
        if (modal) {
          var box = modal.querySelector('.settings-box');
          if (box && holder) {
            box.style.boxShadow = 'none';
            box.style.maxHeight = 'none';
            box.style.width = '100%';
            var head = box.querySelector('.settings-head');
            if (head) head.style.display = 'none';
            holder.appendChild(box);
            holder.style.display = 'block';
          }
        }
        if (window.__ttsAttach) window.__ttsAttach();
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
