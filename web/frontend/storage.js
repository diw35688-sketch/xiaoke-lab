/* 储存库：全局存储位置 + 存储物品资产库 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var TYPE_OPTIONS = [
    ['其他', '其他'], ['溶液', '溶液'], ['种子', '种子'], ['DNA', 'DNA'],
    ['菌液', '菌液'], ['试剂', '试剂'], ['耗材', '耗材'], ['产物', '产物']
  ];
  var STATUS_OPTIONS = [
    ['in_storage', '在库'], ['taken', '已取用'], ['discarded', '已丢弃'], ['expired', '已过期']
  ];

  function statusHtml(s) {
    if (s === 'in_storage') return '<span class="st-badge ok">在库</span>';
    if (s === 'taken') return '<span class="st-badge warn">已取用</span>';
    if (s === 'discarded') return '<span class="st-badge danger">已丢弃</span>';
    if (s === 'expired') return '<span class="st-badge danger">已过期</span>';
    return '<span class="st-badge">' + esc(s || '未知') + '</span>';
  }

  function ensureStyle() {
    if (document.getElementById('storage-page-style')) return;
    var style = document.createElement('style');
    style.id = 'storage-page-style';
    style.textContent = [
      '.storage-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:10px 12px;margin-bottom:12px}',
      '.storage-toolbar input[type=search],.storage-toolbar select{box-sizing:border-box;padding:8px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.storage-toolbar input[type=search]{flex:1;min-width:160px}',
      '.storage-toolbar .sh-btn{white-space:nowrap}',
      '.storage-stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}',
      '.storage-stat{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:8px 14px;font-size:12px;color:#64748b}',
      '.storage-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px;margin-top:12px}',
      '.storage-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;cursor:pointer;transition:border-color .15s,box-shadow .15s}',
      '.storage-card:hover{border-color:#3b67e8;box-shadow:0 4px 12px rgba(59,103,232,.08)}',
      '.storage-card .name{font-weight:700;color:#0f172a}',
      '.storage-card .meta{color:#64748b;font-size:12px;margin-top:4px;line-height:1.6}',
      '.st-badge{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}',
      '.st-badge.ok{background:#dcfce7;color:#15803d}',
      '.st-badge.warn{background:#fef3c7;color:#b45309}',
      '.st-badge.danger{background:#fee2e2;color:#b91c1c}',
      '.storage-form{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:14px;display:none}',
      '.storage-form .frow{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
      '.storage-form label{font-size:12px;color:#475569}',
      '.storage-form input,.storage-form select{width:100%;box-sizing:border-box;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px;font-size:13px;font-family:inherit}',
      '.storage-locations{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-top:16px;display:none}',
      '.storage-locations h4{margin:0 0 10px;font-size:14px;color:#0f172a}',
      '.storage-loc-row{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:13px;color:#334155}',
      '.storage-empty{color:#94a3b8;font-size:13px;margin:20px 0}',
      '@media(max-width:900px){.storage-grid{grid-template-columns:1fr}.storage-form .frow{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function itemCard(item) {
    return '<div class="storage-card" data-id="' + item.id + '">'
      + '<div class="name">' + esc(item.name) + '</div>'
      + '<div class="meta">类型：' + esc(item.item_type) + '</div>'
      + '<div class="meta">数量：' + esc(item.quantity || '—') + ' ' + esc(item.unit || '') + ' · ' + esc(item.concentration || '') + '</div>'
      + '<div class="meta">位置：' + esc(item.location_name || '未分配') + (item.position ? ' / ' + esc(item.position) : '') + '</div>'
      + '<div class="meta">' + statusHtml(item.status) + (item.expires_at ? ' · 到期 ' + esc(item.expires_at) : '') + '</div>'
      + '<div style="margin-top:8px"><button class="sh-btn" type="button" data-edit="' + item.id + '" style="padding:3px 9px;font-size:12px">编辑</button> '
      + '<button class="sh-btn" type="button" data-del="' + item.id + '" style="padding:3px 9px;font-size:12px;color:#b91c1c">删除</button></div>'
      + '</div>';
  }

  window.shellRegisterView('storage', function (host) {
    ensureStyle();
    host.innerHTML = '<div class="storage-toolbar">'
      + '<input type="search" id="st-search" placeholder="搜索名称 / 位置 / 备注…" autocomplete="off">'
      + '<select id="st-type"><option value="">全部类型</option>' + TYPE_OPTIONS.map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join('') + '</select>'
      + '<select id="st-location"><option value="">全部位置</option></select>'
      + '<select id="st-status"><option value="">全部状态</option>' + STATUS_OPTIONS.map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join('') + '</select>'
      + '<button class="sh-btn primary" id="st-add">新增物品</button>'
      + '<button class="sh-btn" id="st-loc-toggle">位置管理</button>'
      + '</div>'
      + '<div class="storage-stats" id="st-stats"></div>'
      + '<div class="storage-form" id="st-form">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px" id="st-form-title">新增物品</div>'
      + '<div class="frow">'
      + '<div><label>名称</label><input id="stf-name" placeholder="如：pUC19 质粒 / 0.1M PBS"></div>'
      + '<div><label>类型</label><select id="stf-type">' + TYPE_OPTIONS.map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join('') + '</select></div>'
      + '<div><label>数量</label><input id="stf-qty" placeholder="如：300"></div>'
      + '<div><label>单位</label><input id="stf-unit" placeholder="mL / 管 / 份"></div>'
      + '<div><label>浓度</label><input id="stf-conc" placeholder="100 ng/μL"></div>'
      + '<div><label>位置</label><select id="stf-location"></select></div>'
      + '<div><label>存放格/标签</label><input id="stf-pos" placeholder="冰箱2层 / A-03"></div>'
      + '<div><label>存放条件</label><input id="stf-condition" placeholder="4℃ / -20℃ / 室温"></div>'
      + '<div><label>存入日期</label><input id="stf-stored" type="date"></div>'
      + '<div><label>到期日期</label><input id="stf-expires" type="date"></div>'
      + '<div><label>状态</label><select id="stf-status">' + STATUS_OPTIONS.map(function (x) { return '<option value="' + x[0] + '">' + x[1] + '</option>'; }).join('') + '</select></div>'
      + '<div style="grid-column:1 / -1"><label>备注</label><input id="stf-notes" placeholder="来源实验/其他说明"></div>'
      + '</div>'
      + '<div style="margin-top:12px;display:flex;gap:8px"><button class="sh-btn primary" id="stf-save">保存</button><button class="sh-btn" id="stf-cancel">取消</button><span id="stf-msg" style="font-size:12px;color:#64748b"></span></div>'
      + '</div>'
      + '<div id="st-list" class="storage-grid">加载中…</div>'
      + '<div class="storage-locations" id="st-locations"><h4>存储位置</h4><div id="st-loc-list"></div>'
      + '<div style="display:flex;gap:8px;margin-top:10px"><input id="st-loc-name" placeholder="位置名称" style="flex:1;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px;font-family:inherit;font-size:13px">'
      + '<input id="st-loc-type" placeholder="类型（冰箱/柜/其他）" style="flex:1;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px;font-family:inherit;font-size:13px">'
      + '<button class="sh-btn" id="st-loc-add">添加</button></div></div>';

    var listEl = host.querySelector('#st-list');
    var searchEl = host.querySelector('#st-search');
    var typeEl = host.querySelector('#st-type');
    var locEl = host.querySelector('#st-location');
    var statusEl = host.querySelector('#st-status');
    var formEl = host.querySelector('#st-form');
    var locPanel = host.querySelector('#st-locations');
    var editId = null;
    var allItems = [];

    function fillLocationSelects(locations) {
      var locOptions = locations.map(function (l) {
        return '<option value="' + l.id + '">' + esc(l.name) + (l.temperature ? ' · ' + esc(l.temperature) : '') + '</option>';
      }).join('');
      host.querySelector('#st-location').innerHTML = '<option value="">全部位置</option>' + locOptions;
      host.querySelector('#stf-location').innerHTML = '<option value="">未分配</option>' + locOptions;
    }

    function load() {
      Promise.all([
        fetch('/storage/stats').then(function (r) { return r.json(); }),
        fetch('/storage/locations').then(function (r) { return r.json(); }),
        var params = new URLSearchParams();
        if (searchEl.value.trim()) params.set('q', searchEl.value.trim());
        if (typeEl.value) params.set('item_type', typeEl.value);
        if (locEl.value) params.set('location_id', locEl.value);
        if (statusEl.value) params.set('status', statusEl.value);
        fetch('/storage/items?' + params.toString()).then(function (r) { return r.json(); })
      ]).then(function (out) {
        var stats = out[0], locations = out[1].items || [], items = out[2].items || [];
        allItems = items;
        fillLocationSelects(locations);
        host.querySelector('#st-stats').innerHTML =
          '<span class="storage-stat">总数 ' + stats.total + '</span>'
          + '<span class="storage-stat">7天内到期 ' + stats.expiring + '</span>'
          + '<span class="storage-stat">已过期 ' + stats.expired + '</span>';
        listEl.innerHTML = items.map(itemCard).join('') || '<div class="storage-empty">暂无存储物品。</div>';
        host.querySelector('#st-loc-list').innerHTML = locations.map(function (l) {
          return '<div class="storage-loc-row"><span><b>' + esc(l.name) + '</b> · ' + esc(l.type) + ' · ' + esc(l.temperature || '') + '</span><button class="sh-btn" type="button" data-del-loc="' + l.id + '" style="padding:2px 7px;font-size:11px;color:#b91c1c">删除</button></div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px">暂无位置</div>';

        Array.prototype.forEach.call(listEl.querySelectorAll('.storage-card'), function (card) {
          card.onclick = function (e) {
            if (e.target.closest('[data-edit]') || e.target.closest('[data-del]')) return;
            var item = allItems.filter(function (x) { return x.id == card.dataset.id; })[0];
            if (item) openForm(item);
          };
        });
        Array.prototype.forEach.call(listEl.querySelectorAll('[data-edit]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var item = allItems.filter(function (x) { return x.id == btn.getAttribute('data-edit'); })[0];
            if (item) openForm(item);
          };
        });
        Array.prototype.forEach.call(listEl.querySelectorAll('[data-del]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            if (!confirm('确定删除这个存储物品？')) return;
            fetch('/storage/items/' + btn.getAttribute('data-del'), { method: 'DELETE' }).then(function () { load(); });
          };
        });
        Array.prototype.forEach.call(host.querySelectorAll('[data-del-loc]'), function (btn) {
          btn.onclick = function () {
            if (!confirm('删除位置后，该位置的物品会变为“未分配”。')) return;
            fetch('/storage/locations/' + btn.getAttribute('data-del-loc'), { method: 'DELETE' }).then(function () { load(); });
          };
        });
      }).catch(function (err) {
        listEl.innerHTML = '<div class="storage-empty">加载失败：' + esc(err.message || err) + '</div>';
      });
    }

    function openForm(item) {
      editId = item ? item.id : null;
      formEl.style.display = 'block';
      formEl.querySelector('#st-form-title').textContent = item ? '编辑物品' : '新增物品';
      formEl.querySelector('#stf-name').value = item ? item.name : '';
      formEl.querySelector('#stf-type').value = item ? item.item_type : '溶液';
      formEl.querySelector('#stf-qty').value = item ? item.quantity : '';
      formEl.querySelector('#stf-unit').value = item ? item.unit : '';
      formEl.querySelector('#stf-conc').value = item ? item.concentration : '';
      formEl.querySelector('#stf-location').value = item && item.location_id ? String(item.location_id) : '';
      formEl.querySelector('#stf-pos').value = item ? item.position : '';
      formEl.querySelector('#stf-condition').value = item ? item.storage_condition : '';
      formEl.querySelector('#stf-stored').value = item ? (item.stored_at || '').slice(0, 10) : '';
      formEl.querySelector('#stf-expires').value = item ? (item.expires_at || '').slice(0, 10) : '';
      formEl.querySelector('#stf-status').value = item ? item.status : 'in_storage';
      formEl.querySelector('#stf-notes').value = item ? item.notes : '';
      formEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function collect() {
      return {
        item_type: formEl.querySelector('#stf-type').value,
        name: formEl.querySelector('#stf-name').value.trim(),
        quantity: formEl.querySelector('#stf-qty').value.trim(),
        unit: formEl.querySelector('#stf-unit').value.trim(),
        concentration: formEl.querySelector('#stf-conc').value.trim(),
        location_id: formEl.querySelector('#stf-location').value ? parseInt(formEl.querySelector('#stf-location').value, 10) : null,
        position: formEl.querySelector('#stf-pos').value.trim(),
        storage_condition: formEl.querySelector('#stf-condition').value.trim(),
        stored_at: formEl.querySelector('#stf-stored').value,
        expires_at: formEl.querySelector('#stf-expires').value,
        status: formEl.querySelector('#stf-status').value,
        notes: formEl.querySelector('#stf-notes').value.trim(),
        owner: ''
      };
    }

    host.querySelector('#st-add').onclick = function () { openForm(null); };
    host.querySelector('#stf-cancel').onclick = function () { formEl.style.display = 'none'; editId = null; };
    host.querySelector('#stf-save').onclick = function () {
      var data = collect();
      if (!data.name) { host.querySelector('#stf-msg').textContent = '名称不能为空'; return; }
      var url = editId ? '/storage/items/' + editId : '/storage/items';
      var method = editId ? 'PATCH' : 'POST';
      fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
        .then(function (r) { return r.json(); }).then(function (d) {
          if (d.detail) { host.querySelector('#stf-msg').textContent = d.detail; return; }
          formEl.style.display = 'none'; editId = null; host.querySelector('#stf-msg').textContent = '';
          load();
        }).catch(function (err) { host.querySelector('#stf-msg').textContent = err.message; });
    };
    host.querySelector('#st-loc-toggle').onclick = function () {
      locPanel.style.display = locPanel.style.display === 'block' ? 'none' : 'block';
    };
    host.querySelector('#st-loc-add').onclick = function () {
      var name = host.querySelector('#st-loc-name').value.trim();
      if (!name) return;
      fetch('/storage/locations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name, type: host.querySelector('#st-loc-type').value.trim() || '其他' }) })
        .then(function () { host.querySelector('#st-loc-name').value = ''; host.querySelector('#st-loc-type').value = ''; load(); });
    };

    searchEl.addEventListener('input', load);
    typeEl.addEventListener('change', load);
    locEl.addEventListener('change', load);
    statusEl.addEventListener('change', load);
    load();
  });
})();
