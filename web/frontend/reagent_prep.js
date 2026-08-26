/* 试剂配置库页面：查看配方、上传用户自己的 JSON 配置库。 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function badgeHtml(status) {
    if (status === 'REVIEWED') {
      return '<span class="prep-badge reviewed">已复核</span>';
    }
    return '<span class="prep-badge unreviewed">未复核</span>';
  }

  function renderPrep(p) {
    return '<div class="prep-card" data-id="' + esc(p.reagent_prep_id) + '" data-name="' + esc(p.name_zh.toLowerCase()) + '" data-purpose="' + esc((p.purpose || '').toLowerCase()) + '">'
      + '<div class="prep-card-head"><div class="prep-name">' + esc(p.name_zh) + '</div>' + badgeHtml(p.review_status) + '</div>'
      + '<div class="prep-purpose">' + esc(p.purpose) + '</div>'
      + '<div class="prep-target">目标：' + esc(p.target_concentration || '未指定') + ' · 体积：' + esc(p.target_volume || '按需') + ' · 溶剂：' + esc(p.solvent || '未指定') + '</div>'
      + '<div class="prep-actions"><button class="sh-btn" type="button" data-detail="' + esc(p.reagent_prep_id) + '">查看配置</button></div>'
      + '</div>';
  }

  function showPrepDetail(host, prep) {
    function render() {
      var steps = (prep.steps || []).map(function (s, i) {
        return '<div class="prep-step">' + (i + 1) + '. ' + esc(s) + '</div>';
      }).join('');
      var safety = (prep.safety || []).map(function (s) {
        return '<div class="prep-safety">⚠ ' + esc(s.name) + '：' + esc((s.statements || []).join('；')) + '</div>';
      }).join('');
      var badge = badgeHtml(prep.review_status);
      host.innerHTML = '<div class="prep-detail">'
        + '<div style="display:flex;gap:8px;justify-content:space-between;align-items:center"><button class="sh-btn" id="prep-back">← 返回配置列表</button>'
        + '<div><button class="sh-btn" id="prep-edit">编辑此配方</button><button class="sh-btn" id="prep-del" style="color:#b91c1c;margin-left:6px">删除配方</button></div></div>'
        + '<div class="prep-detail-title">' + esc(prep.name_zh) + '</div>'
        + '<div class="prep-detail-sub">' + esc(prep.purpose) + ' · ' + badge + '</div>'
        + '<div class="prep-detail-box">'
        + '<div>目标：' + esc(prep.target_concentration || '未指定') + '</div>'
        + '<div>体积：' + esc(prep.target_volume || '按需') + '</div>'
        + '<div>溶剂：' + esc(prep.solvent || '未指定') + '</div>'
        + '<div>保存：' + esc(prep.storage_condition || '未指定') + '</div>'
        + '<div>有效期：' + esc(prep.expiry || '未指定') + '</div>'
        + '</div>'
        + '<div class="prep-section-title">配制步骤</div>'
        + '<div class="prep-detail-box">' + (steps || '<div style="color:#94a3b8">暂无步骤</div>') + '</div>'
        + (safety ? '<div class="prep-section-title">安全提示</div><div class="prep-detail-box prep-safety-box">' + safety + '</div>' : '')
        + '<div class="prep-source">来源：' + esc(prep.source || '未注明') + (prep.source_url ? ' · <a href="' + esc(prep.source_url) + '" target="_blank">查看来源</a>' : '') + '</div>'
        + '</div>';
      host.querySelector('#prep-back').onclick = function () { window.shellShow('reagent_prep'); };
      host.querySelector('#prep-edit').onclick = function () { showEdit(); };
      host.querySelector('#prep-del').onclick = function () {
        if (!confirm('确定删除这个配方？')) return;
        fetch('/reagent-prep/' + encodeURIComponent(prep.reagent_prep_id), { method: 'DELETE' }).then(function () {
          window.shellShow('reagent_prep');
        });
      };
    }

    function showEdit() {
      var editSteps = (prep.steps || []).slice();
      host.innerHTML = '<div class="prep-detail" style="max-width:900px">'
        + '<button class="sh-btn" id="prep-edit-back">← 返回详情</button>'
        + '<div class="prep-detail-title">编辑配方</div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
        + '<div><label style="font-size:12px;color:#475569">名称</label><input id="pe-name" value="' + esc(prep.name_zh || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">用途</label><input id="pe-purpose" value="' + esc(prep.purpose || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">目标浓度</label><input id="pe-conc" value="' + esc(prep.target_concentration || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">目标体积</label><input id="pe-vol" value="' + esc(prep.target_volume || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">溶剂</label><input id="pe-solvent" value="' + esc(prep.solvent || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">保存条件</label><input id="pe-storage" value="' + esc(prep.storage_condition || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div><label style="font-size:12px;color:#475569">有效期</label><input id="pe-expiry" value="' + esc(prep.expiry || '') + '" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '</div>'
        + '<div style="margin-top:12px"><label style="font-size:12px;color:#475569">配制步骤（每行一步，可用加号连接）</label><div id="pe-steps-list"></div><button class="sh-btn" id="pe-add-step" type="button" style="margin-top:6px">＋ 添加步骤</button></div>'
        + '<div style="margin-top:12px"><label style="font-size:12px;color:#475569;background:#f0f9ff;padding:4px 8px;border-radius:6px">保存后会自动识别步骤中的试剂名称并关联安全提示</label></div>'
        + '<div style="margin-top:12px;display:flex;gap:8px"><button class="sh-btn primary" id="pe-save">保存</button><button class="sh-btn" id="pe-cancel">取消</button><span id="pe-msg" style="font-size:12px;color:#64748b"></span></div>'
        + '</div>';
      function renderStepRows() {
        var container = host.querySelector('#pe-steps-list');
        container.innerHTML = editSteps.map(function (s, i) {
          return '<div class="pe-step-row" style="display:flex;gap:6px;margin-top:6px;align-items:center">'
            + '<span style="width:24px;text-align:right;color:#94a3b8;font-size:12px;flex:0 0 auto">' + (i + 1) + '.</span>'
            + '<input class="pe-step-input" data-idx="' + i + '" value="' + esc(s) + '" placeholder="如：加入 1 mL 盐酸 + 2 mL 水" style="flex:1;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px;font-family:inherit">'
            + '<button class="sh-btn" data-del-step="' + i + '" type="button" style="color:#b91c1c;padding:4px 8px;font-size:11px">删除</button>'
            + '</div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px;margin-top:6px">暂无步骤，点“添加步骤”</div>';
        Array.prototype.forEach.call(container.querySelectorAll('.pe-step-input'), function (input) {
          input.oninput = function () {
            var idx = parseInt(input.getAttribute('data-idx'), 10);
            editSteps[idx] = input.value;
          };
        });
        Array.prototype.forEach.call(container.querySelectorAll('[data-del-step]'), function (btn) {
          btn.onclick = function () {
            var idx = parseInt(btn.getAttribute('data-del-step'), 10);
            editSteps.splice(idx, 1);
            renderStepRows();
          };
        });
      }
      renderStepRows();
      host.querySelector('#prep-edit-back').onclick = render;
      host.querySelector('#pe-cancel').onclick = render;
      host.querySelector('#pe-add-step').onclick = function () {
        editSteps.push('');
        renderStepRows();
        var inputs = host.querySelectorAll('.pe-step-input');
        if (inputs.length) inputs[inputs.length - 1].focus();
      };
      host.querySelector('#pe-save').onclick = function () {
        var updated = {
          reagent_prep_id: prep.reagent_prep_id,
          name_zh: host.querySelector('#pe-name').value.trim(),
          purpose: host.querySelector('#pe-purpose').value.trim(),
          target_concentration: host.querySelector('#pe-conc').value.trim(),
          target_volume: host.querySelector('#pe-vol').value.trim(),
          solvent: host.querySelector('#pe-solvent').value.trim(),
          storage_condition: host.querySelector('#pe-storage').value.trim(),
          expiry: host.querySelector('#pe-expiry').value.trim(),
          steps: editSteps.map(function (x) { return x.trim(); }).filter(Boolean)
        };
        fetch('/reagent-prep/' + encodeURIComponent(prep.reagent_prep_id), {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reagent_prep: updated })
        }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (res) {
          if (!res.ok) { host.querySelector('#pe-msg').textContent = res.d.detail || '保存失败'; return; }
          prep = res.d;
          render();
        }).catch(function (e) { host.querySelector('#pe-msg').textContent = e.message; });
      };
    }

    render();
  }

  function ensureStyles(host) {
    if (document.getElementById('prep-grid-style')) return;
    var style = document.createElement('style');
    style.id = 'prep-grid-style';
    style.textContent = [
      '.prep-card{background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:12px 14px;cursor:pointer;transition:border-color .15s,box-shadow .15s}',
      '.prep-card:hover{border-color:var(--brand,#3b67e8);box-shadow:0 4px 12px rgba(59,103,232,.08)}',
      '.prep-card-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}',
      '.prep-name{font-weight:700;color:#0f172a;line-height:1.3}',
      '.prep-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap;flex:0 0 auto}',
      '.prep-badge.reviewed{background:#dcfce7;color:#15803d}',
      '.prep-badge.unreviewed{background:#fef3c7;color:#b45309}',
      '.prep-purpose{color:#64748b;font-size:13px;margin-top:4px}',
      '.prep-target{color:#334155;font-size:13px;margin-top:6px;line-height:1.5}',
      '.prep-actions{margin-top:9px}',
      '.prep-actions .sh-btn{padding:3px 9px;font-size:12px}',
      '.prep-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:10px 12px;margin-bottom:12px}',
      '.prep-toolbar .search-wrap{flex:1;min-width:180px}',
      '.prep-toolbar input[type=search]{width:100%;box-sizing:border-box;padding:8px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.prep-toolbar input[type=search]:focus{outline:2px solid rgba(59,103,232,.25);border-color:var(--brand,#3b67e8)}',
      '.prep-toolbar .sh-btn{white-space:nowrap}',
      '.prep-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-top:12px}',
      '.prep-empty{color:#94a3b8;font-size:13px;margin:20px 0}',
      '.prep-detail{max-width:1024px}',
      '.prep-detail-title{font-size:20px;font-weight:700;color:#0f172a;margin:16px 0 4px}',
      '.prep-detail-sub{color:#64748b;font-size:13px;margin-bottom:14px}',
      '.prep-detail-box{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:12px;color:#334155;font-size:13px;line-height:1.8}',
      '.prep-step{margin:4px 0 0 18px;color:#475569;font-size:13px}',
      '.prep-section-title{font-size:14px;font-weight:700;color:#0f172a;margin:12px 0 8px}',
      '.prep-safety-box{border-color:#fee2e2}',
      '.prep-safety{color:#b91c1c;font-size:12px;margin-top:6px}',
      '.prep-source{color:#94a3b8;font-size:12px;margin-top:10px}',
      '@media(max-width:900px){.prep-list{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  window.shellRegisterView('reagent_prep', function (host) {
    ensureStyles(host);

    host.innerHTML = '<div class="prep-page">'
      + '<div class="prep-toolbar">'
      + '<input type="search" id="prep-search" placeholder="搜索试剂名称 / 用途…" autocomplete="off">'
      + '<input type="file" id="prep-file" accept=".json,application/json" style="display:none">'
      + '<button class="sh-btn" id="prep-file-btn">选择文件</button>'
      + '<button class="sh-btn" id="prep-upload">上传 JSON</button>'
      + '<button class="sh-btn primary" id="prep-chat-create">AI 生成</button>'
      + '<button class="sh-btn" id="prep-safety-btn" title="安全信息来自 PubChem / GB 30000，仅作引用展示">安全参考</button>'
      + '<span id="prep-upload-msg" style="font-size:12px;color:#64748b"></span>'
      + '</div>'
      + '<div style="color:#64748b;font-size:12px;margin:-4px 0 8px">JSON 格式：{"reagent_preps":[{...}]}，字段见契约说明。上传会严格校验，不通过不落盘。</div>'
      + '<div id="prep-form-box" style="display:none;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:14px">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px">填写试剂配置信息</div>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
      + '<div><label style="font-size:12px;color:#475569">试剂名称</label><input id="pf-name" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：PBS 缓冲液"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标浓度</label><input id="pf-conc" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：0.1 mol/L"></div>'
      + '<div><label style="font-size:12px;color:#475569">体积</label><input id="pf-vol" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：500 mL"></div>'
      + '<div><label style="font-size:12px;color:#475569">溶剂</label><input id="pf-solvent" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：超纯水 / DMSO"></div>'
      + '<div><label style="font-size:12px;color:#475569">保存条件</label><input id="pf-storage" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：4℃ 避光"></div>'
      + '<div><label style="font-size:12px;color:#475569">有效期</label><input id="pf-expiry" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：1 个月"></div>'
      + '<div style="grid-column:1 / -1"><label style="font-size:12px;color:#475569">用途</label><input id="pf-purpose" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：细胞洗涤、Western blot 转膜缓冲液"></div>'
      + '</div>'
      + '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">'
      + '<button class="sh-btn primary" id="pf-send">生成并发送</button>'
      + '<button class="sh-btn" id="pf-cancel">取消</button>'
      + '<span id="pf-msg" style="font-size:12px;color:#64748b"></span>'
      + '</div>'
      + '</div>'
      + '<div id="prep-safety-box" style="display:none"></div>'
      + '<div id="prep-list" class="prep-list">加载中…</div>'
      + '</div>';

    function showSafety() {
      var box = host.querySelector('#prep-safety-box');
      var list = host.querySelector('#prep-list');
      box.style.display = '';
      list.style.display = 'none';
      box.innerHTML = '加载安全参考…';
      fetch('/protocols/reagents').then(function (r) { return r.json(); }).then(function (d) {
        var items = d.reagents || [];
        box.innerHTML = '<div style="display:flex;gap:8px;align-items:center;justify-content:space-between;margin-bottom:10px">'
          + '<div><b style="color:#0f172a">安全参考</b> <span style="color:#64748b;font-size:12px">共 ' + d.count + ' 种 · 数据来自 PubChem / GB 30000，仅引用展示</span></div>'
          + '<button class="sh-btn" id="prep-safety-back">返回配置库</button></div>'
          + '<div style="color:#94a3b8;font-size:12px;margin-bottom:8px">' + esc(d.note || '') + '</div>'
          + '<input type="search" id="prep-safety-search" placeholder="搜索试剂名称 / CAS / 分子式…" autocomplete="off" style="width:100%;box-sizing:border-box;padding:8px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;margin-bottom:12px">'
          + '<div id="prep-safety-grid" class="prep-list" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))"></div>';
        function render(items) {
          var grid = host.querySelector('#prep-safety-grid');
          grid.innerHTML = items.map(function (r) {
            return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px">'
              + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b>' + esc(r.name) + '</b>'
              + (r.critical ? '<span style="background:#fee2e2;color:#b91c1c;border-radius:999px;padding:2px 9px;font-size:11px;white-space:nowrap;max-width:170px;overflow:hidden;text-overflow:ellipsis">高危</span>' : '<span style="color:#94a3b8;font-size:12px">无高危项</span>')
              + '</div>'
              + '<div style="color:#64748b;font-size:12px;margin-top:5px">CAS ' + esc(r.cas || '—') + ' · ' + esc(r.formula || '') + '</div>'
              + '<div style="margin-top:6px">' + (r.statements || []).slice(0, 2).map(function (s) { return '<div style="color:#475569;font-size:11px">' + esc(s) + '</div>'; }).join('') + '</div>'
              + '</div>';
          }).join('') || '<div style="color:#94a3b8">没有匹配的试剂。</div>';
        }
        render(items);
        var s = host.querySelector('#prep-safety-search');
        s.addEventListener('input', function () {
          var q = s.value.trim().toLowerCase();
          render(items.filter(function (r) {
            return !q || (r.name || '').toLowerCase().indexOf(q) >= 0 || (r.cas || '').toLowerCase().indexOf(q) >= 0 || (r.formula || '').toLowerCase().indexOf(q) >= 0;
          }));
        });
        host.querySelector('#prep-safety-back').onclick = function () {
          box.style.display = 'none';
          list.style.display = '';
        };
      });
    }

    function load(filterText) {
      fetch('/reagent-prep').then(function (r) { return r.json(); }).then(function (d) {
        var items = (d.items || []).filter(function (p) {
          if (!filterText) return true;
          var q = filterText.toLowerCase();
          return (p.name_zh || '').toLowerCase().indexOf(q) >= 0 || (p.purpose || '').toLowerCase().indexOf(q) >= 0;
        });
        host.querySelector('#prep-list').innerHTML = items.map(renderPrep).join('') || '<div class="prep-empty">没有匹配的试剂配置。</div>';
        Array.prototype.forEach.call(host.querySelectorAll('.prep-card'), function (card) {
          card.onclick = function (e) {
            if (e.target.closest('[data-detail]')) return;
            var item = (d.items || []).filter(function (x) { return x.reagent_prep_id === card.dataset.id; })[0];
            if (item) showPrepDetail(host, item);
          };
        });
        Array.prototype.forEach.call(host.querySelectorAll('.prep-actions [data-detail]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-detail');
            var item = (d.items || []).filter(function (x) { return x.reagent_prep_id === id; })[0];
            if (item) showPrepDetail(host, item);
          };
        });
      });
    }

    var searchInput = host.querySelector('#prep-search');
    searchInput.addEventListener('input', function () { load(searchInput.value.trim()); });

    host.querySelector('#prep-file-btn').onclick = function () { host.querySelector('#prep-file').click(); };
    host.querySelector('#prep-chat-create').onclick = function () {
      var box = host.querySelector('#prep-form-box');
      box.style.display = '';
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      var nameInput = host.querySelector('#pf-name');
      if (nameInput) nameInput.focus();
    };

    host.querySelector('#prep-safety-btn').onclick = showSafety;

    host.querySelector('#pf-send').onclick = function () {
      var parts = [];
      var name = (host.querySelector('#pf-name').value || '').trim();
      var conc = (host.querySelector('#pf-conc').value || '').trim();
      var vol = (host.querySelector('#pf-vol').value || '').trim();
      var solvent = (host.querySelector('#pf-solvent').value || '').trim();
      var storage = (host.querySelector('#pf-storage').value || '').trim();
      var expiry = (host.querySelector('#pf-expiry').value || '').trim();
      var purpose = (host.querySelector('#pf-purpose').value || '').trim();
      if (name) parts.push('试剂：' + name);
      if (conc) parts.push('浓度：' + conc);
      if (vol) parts.push('体积：' + vol);
      if (solvent) parts.push('溶剂：' + solvent);
      if (storage) parts.push('保存条件：' + storage);
      if (expiry) parts.push('有效期：' + expiry);
      if (purpose) parts.push('用途：' + purpose);
      if (!parts.length) { host.querySelector('#pf-msg').textContent = '请至少填写一项'; return; }
      var text = '请根据以下要求创建一条试剂配置：' + parts.join('，') + '。';
      if (typeof window.composerSend === 'function') window.composerSend(text);
      host.querySelector('#prep-form-box').style.display = 'none';
    };

    host.querySelector('#pf-cancel').onclick = function () {
      host.querySelector('#prep-form-box').style.display = 'none';
    };

    host.querySelector('#prep-upload').onclick = function () {
      var input = host.querySelector('#prep-file');
      var msg = host.querySelector('#prep-upload-msg');
      if (!input.files || !input.files[0]) { msg.textContent = '请先选择 JSON 文件'; return; }
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          var payload = { reagent_preps: data.reagent_preps || [data] };
          fetch('/reagent-prep/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
          }).then(function (res) {
            if (!res.ok) { msg.textContent = res.d.detail || '上传失败'; return; }
            msg.textContent = '已新增 ' + res.d.added + ' 条';
            load(searchInput.value.trim());
          }).catch(function (e) { msg.textContent = '上传失败：' + e.message; });
        } catch (e) {
          msg.textContent = 'JSON 解析失败：' + e.message;
        }
      };
      reader.readAsText(input.files[0]);
    };

    load('');
  });
})();
