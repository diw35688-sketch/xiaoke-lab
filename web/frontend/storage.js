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
      '.storage-map-toolbar{display:flex;gap:8px;align-items:center;margin-top:10px}',
      '.storage-view-btn{border:1px solid #e2e8f0;background:#fff;border-radius:999px;padding:4px 12px;font-size:12px;cursor:pointer;color:#64748b}',
      '.storage-view-btn.active{background:#2563eb;color:#fff;border-color:#2563eb}',
      '.storage-map{display:flex;gap:14px;overflow-x:auto;padding:4px 0 16px;margin-top:12px;align-items:flex-start}',
      '.storage-map-loc{flex:0 0 260px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:12px;min-height:200px;transition:border-color .15s,background .15s}',
      '.storage-map-loc.dragover{border-color:#3b67e8;background:#eff6ff}',
      '.storage-map-loc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:2px}',
      '.storage-map-loc-sub{color:#94a3b8;font-size:11px;margin-bottom:8px}',
      '.storage-map-slot{margin-top:8px;border:1px dashed #e2e8f0;border-radius:10px;padding:8px;min-height:58px;background:#f8fafc}',
      '.storage-map-slot.dragover{border-color:#3b67e8;background:#f0f9ff}',
      '.storage-map-slot-title{font-size:11px;color:#64748b;font-weight:600;margin-bottom:4px}',
      '.storage-chip{display:block;background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:5px 7px;margin-bottom:5px;cursor:grab;font-size:11px;line-height:1.4;box-shadow:0 1px 3px rgba(15,23,42,.05)}',
      '.storage-chip.dragging{opacity:.5}',
      '.storage-chip .tn{font-weight:600;color:#0f172a}',
      '.storage-chip .tm{color:#94a3b8;font-size:10px}',
      '.storage-map-empty{color:#94a3b8;font-size:12px;padding:20px 0}',
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
      + '<span class="storage-map-toolbar"><button type="button" class="storage-view-btn active" id="st-view-list">列表</button><button type="button" class="storage-view-btn" id="st-view-map">地图</button></span>'
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
      + '<div id="st-map" class="storage-map" style="display:none"></div>'
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
    var mapMode = false;

    function fillLocationSelects(locations) {
      var locOptions = locations.map(function (l) {
        return '<option value="' + l.id + '">' + esc(l.name) + (l.temperature ? ' · ' + esc(l.temperature) : '') + '</option>';
      }).join('');
      host.querySelector('#st-location').innerHTML = '<option value="">全部位置</option>' + locOptions;
      host.querySelector('#stf-location').innerHTML = '<option value="">未分配</option>' + locOptions;
    }

    function renderMap(locations, items) {
      var map = host.querySelector('#st-map');
      var locMap = {};
      locations.forEach(function (l) { locMap[l.id] = l; });
      var unassigned = items.filter(function (i) { return !i.location_id; });
      var assigned = items.filter(function (i) { return i.location_id; });
      map.innerHTML = locations.map(function (loc) {
        var locItems = assigned.filter(function (i) { return i.location_id == loc.id; });
        var groups = {};
        locItems.forEach(function (i) {
          var key = i.position || '未分格';
          (groups[key] = groups[key] || []).push(i);
        });
        var slots = Object.keys(groups).map(function (key) {
          var chips = groups[key].map(function (i) {
            return '<div class="storage-chip" draggable="true" data-id="' + i.id + '">'
              + '<div class="tn">' + esc(i.name) + '</div>'
              + '<div class="tm">' + esc(i.quantity || '') + ' ' + esc(i.unit || '') + ' · ' + statusHtml(i.status) + '</div></div>';
          }).join('');
          return '<div class="storage-map-slot" data-loc="' + loc.id + '" data-pos="' + esc(key) + '"><div class="storage-map-slot-title">' + esc(key) + '</div>' + (chips || '<div style="color:#cbd5e1;font-size:11px">空</div>') + '</div>';
        }).join('') || '<div class="storage-map-slot" data-loc="' + loc.id + '" data-pos=""><div class="storage-map-slot-title">未分格</div><div style="color:#cbd5e1;font-size:11px">空</div></div>';
        return '<div class="storage-map-loc" data-loc="' + loc.id + '">'
          + '<div class="storage-map-loc-title">' + esc(loc.name) + '</div>'
          + '<div class="storage-map-loc-sub">' + esc(loc.type || '') + (loc.temperature ? ' · ' + esc(loc.temperature) : '') + ' · ' + locItems.length + ' 项</div>'
          + slots
          + '</div>';
      }).join('') + (unassigned.length ? '<div class="storage-map-loc" data-loc="" style="border-style:dashed"><div class="storage-map-loc-title">未分配</div><div class="storage-map-loc-sub">' + unassigned.length + ' 项</div><div class="storage-map-slot" data-loc="" data-pos=""><div class="storage-map-slot-title">拖到这里</div>' + unassigned.map(function (i) {
        return '<div class="storage-chip" draggable="true" data-id="' + i.id + '"><div class="tn">' + esc(i.name) + '</div><div class="tm">' + esc(i.quantity || '') + ' ' + esc(i.unit || '') + '</div></div>';
      }).join('') + '</div></div>' : '');

      Array.prototype.forEach.call(map.querySelectorAll('.storage-chip'), function (chip) {
        chip.addEventListener('dragstart', function (e) {
          e.dataTransfer.setData('text/plain', chip.getAttribute('data-id'));
          chip.classList.add('dragging');
        });
        chip.addEventListener('dragend', function () { chip.classList.remove('dragging'); });
      });
      Array.prototype.forEach.call(map.querySelectorAll('.storage-map-loc, .storage-map-slot'), function (zone) {
        zone.addEventListener('dragover', function (e) { e.preventDefault(); zone.classList.add('dragover'); });
        zone.addEventListener('dragleave', function () { zone.classList.remove('dragover'); });
        zone.addEventListener('drop', function (e) {
          e.preventDefault();
          zone.classList.remove('dragover');
          var id = e.dataTransfer.getData('text/plain');
          if (!id) return;
          var locId = zone.getAttribute('data-loc') || null;
          var pos = zone.getAttribute('data-pos') || '';
          fetch('/storage/items/' + id, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ location_id: locId ? parseInt(locId, 10) : null, position: pos })
          }).then(function () { load(); });
        });
      });
    }

    function load() {
      var params = new URLSearchParams();
      if (searchEl.value.trim()) params.set('q', searchEl.value.trim());
      if (typeEl.value) params.set('item_type', typeEl.value);
      if (locEl.value) params.set('location_id', locEl.value);
      if (statusEl.value) params.set('status', statusEl.value);
      Promise.all([
        fetch('/storage/stats').then(function (r) { return r.json(); }),
        fetch('/storage/locations').then(function (r) { return r.json(); }),
        fetch('/storage/items?' + params.toString()).then(function (r) { return r.json(); })
      ]).then(function (out) {
        var stats = out[0], locations = out[1].items || [], items = out[2].items || [];
        allItems = items;
        fillLocationSelects(locations);
        host.querySelector('#st-stats').innerHTML =
          '<span class="storage-stat">总数 ' + stats.total + '</span>'
          + '<span class="storage-stat">7天内到期 ' + stats.expiring + '</span>'
          + '<span class="storage-stat">已过期 ' + stats.expired + '</span>';
        if (mapMode) {
          host.querySelector('#st-list').style.display = 'none';
          host.querySelector('#st-map').style.display = '';
          renderMap(locations, items);
        } else {
          host.querySelector('#st-map').style.display = 'none';
          host.querySelector('#st-list').style.display = '';
          listEl.innerHTML = items.map(itemCard).join('') || '<div class="storage-empty">暂无存储物品。</div>';
        }
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
    var listBtn = host.querySelector('#st-view-list');
    var mapBtn = host.querySelector('#st-view-map');
    listBtn.onclick = function () { mapMode = false; listBtn.classList.add('active'); mapBtn.classList.remove('active'); load(); };
    mapBtn.onclick = function () { mapMode = true; mapBtn.classList.add('active'); listBtn.classList.remove('active'); load(); };
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
