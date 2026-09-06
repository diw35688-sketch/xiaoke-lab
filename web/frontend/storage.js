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
      '.storage-tree{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;margin-top:12px}',
      '.tree-node{cursor:pointer;padding:6px 8px;border-radius:8px;position:relative}',
      '.tree-node:hover{background:#f8fafc}',
      '.tree-node.dragover{background:#eff6ff;outline:2px solid rgba(59,103,232,.25)}',
      '.tree-caret{display:inline-block;width:14px;color:#94a3b8;font-size:10px;transition:transform .15s}',
      '.tree-node.open .tree-caret{transform:rotate(90deg)}',
      '.tree-loc{font-weight:700;color:#0f172a;font-size:13px}',
      '.tree-loc-sub{color:#94a3b8;font-size:11px;margin-left:4px}',
      '.tree-children{padding-left:22px;display:none}',
      '.tree-node.open>.tree-children{display:block}',
      '.tree-slot{display:flex;align-items:center;gap:8px;color:#475569;font-size:12px;padding:4px 0}',
      '.tree-item{display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:8px;cursor:grab;background:#f8fafc;border:1px solid #eef2f7;margin:3px 0}',
      '.tree-item.dragging{opacity:.5}',
      '.tree-item .tn{font-weight:600;color:#0f172a;font-size:12px}',
      '.tree-item .tm{color:#94a3b8;font-size:11px}',
      '.tree-item .st-badge{margin-left:auto}',
      '.storage-racks{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px}',
      '.rack{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;min-width:260px}',
      '.rack-title{font-weight:700;color:#0f172a;font-size:14px;margin-bottom:2px}',
      '.rack-sub{color:#94a3b8;font-size:11px;margin-bottom:10px}',
      '.rack-grid{display:grid;gap:6px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:10px;padding:8px}',
      '.rack-cell{background:#fff;border:1px dashed #cbd5e1;border-radius:8px;min-height:56px;padding:5px;position:relative;transition:border-color .15s,background .15s}',
      '.rack-cell.dragover{border-color:#3b67e8;background:#eff6ff}',
      '.rack-cell .cell-label{font-size:10px;color:#94a3b8;margin-bottom:3px}',
      '.rack-item{display:block;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:4px 5px;font-size:11px;cursor:grab;line-height:1.3;margin-bottom:3px}',
      '.rack-item.dragging{opacity:.5}',
      '.rack-item .rn{font-weight:600;color:#1d4ed8}',
      '.rack-item .rm{color:#64748b;font-size:10px}',
      '.rack-other{margin-top:8px;border:1px dashed #fecaca;border-radius:10px;padding:8px;background:#fff7ed}',
      '.rack-other .cell-label{font-size:10px;color:#b45309;margin-bottom:4px}',
      '.storage-map-empty{color:#94a3b8;font-size:12px;padding:20px 0}',
      '.storage-canvas{position:relative;height:640px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;overflow:auto;margin-top:12px;background-image:linear-gradient(#eef2f7 1px,transparent 1px),linear-gradient(90deg,#eef2f7 1px,transparent 1px);background-size:24px 24px}',
      '.storage-canvas .hint{position:absolute;left:16px;top:12px;color:#94a3b8;font-size:12px;pointer-events:none}',
      '.canvas-loc{position:absolute;background:#fff;border:1px solid #cbd5e1;border-radius:12px;padding:9px 11px;box-shadow:0 3px 12px rgba(15,23,42,.06);cursor:move;min-width:170px;max-width:300px;user-select:none}',
      '.canvas-loc.dragging{box-shadow:0 8px 24px rgba(15,23,42,.16);opacity:.95;z-index:5}',
      '.canvas-loc .cl-title{font-weight:700;color:#0f172a;font-size:13px}',
      '.canvas-loc .cl-sub{color:#94a3b8;font-size:11px;margin:2px 0 6px}',
      '.canvas-loc .cl-actions{display:flex;gap:4px;margin-top:5px}',
      '.canvas-loc .cl-actions .sh-btn{padding:2px 7px;font-size:11px}',
      '.canvas-loc .cl-count{display:inline-block;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:1px 7px;font-size:10px;margin-left:5px}',

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
    var provenanceBadge = '';
    if (item.source_experiment_id) {
      provenanceBadge = '<div class="meta" style="color:#7c3aed"><span style="display:inline-block;background:#ede9fe;color:#7c3aed;padding:1px 7px;border-radius:5px;font-size:11px">🔬 实验产物</span> 来自 ' + esc(String(item.source_experiment_id).slice(0, 30)) + '</div>';
    }
    return '<div class="storage-card" data-id="' + item.id + '">'
      + '<div class="name">' + esc(item.name) + '</div>'
      + '<div class="meta">类型：' + esc(item.item_type) + '</div>'
      + '<div class="meta">数量：' + esc(item.quantity || '—') + ' ' + esc(item.unit || '') + ' · ' + esc(item.concentration || '') + '</div>'
      + '<div class="meta">位置：' + esc(item.location_name || '未分配') + (item.position ? ' / ' + esc(item.position) : '') + '</div>'
      + '<div class="meta">' + statusHtml(item.status) + (item.expires_at ? ' · 到期 ' + esc(item.expires_at) : '') + '</div>'
      + provenanceBadge
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
    var allLocations = [];
    var mapMode = false;

    function fillLocationSelects(locations) {
      var locOptions = locations.map(function (l) {
        return '<option value="' + l.id + '">' + esc(l.name) + (l.temperature ? ' · ' + esc(l.temperature) : '') + '</option>';
      }).join('');
      host.querySelector('#st-location').innerHTML = '<option value="">全部位置</option>' + locOptions;
      host.querySelector('#stf-location').innerHTML = '<option value="">未分配</option>' + locOptions;
    }

    function locationBoxHtml(loc, assigned) {
      var locItems = assigned.filter(function (i) { return i.location_id == loc.id; });
      var rows = parseInt(loc.grid_rows, 10) || 2;
      var cols = parseInt(loc.grid_cols, 10) || 4;
      var mini = '<div style="display:grid;grid-template-columns:repeat(' + cols + ',1fr);gap:3px;margin-top:5px">';
      for (var r = 0; r < rows; r += 1) {
        for (var c = 0; c < cols; c += 1) {
          var label = String.fromCharCode(65 + r) + '-' + String(c + 1).toString().padStart(2, '0');
          var cellItems = locItems.filter(function (i) { return (i.position || '') === label; });
          mini += '<div style="min-height:18px;border-radius:4px;border:1px dashed #e2e8f0;background:#f8fafc;font-size:9px;line-height:18px;text-align:center;color:#94a3b8">' + (cellItems.length ? esc(cellItems[0].name.slice(0, 6)) : label) + '</div>';
        }
      }
      mini += '</div>';
      return '<div class="canvas-loc" data-loc="' + loc.id + '" style="left:' + (loc.map_x || 0) + 'px;top:' + (loc.map_y || 0) + 'px">'
        + '<div class="cl-title">' + esc(loc.name) + '<span class="cl-count">' + locItems.length + '</span></div>'
        + '<div class="cl-sub">' + esc(loc.type || '') + (loc.temperature ? ' · ' + esc(loc.temperature) : '') + ' · ' + rows + '×' + cols + '</div>'
        + mini
        + '<div class="cl-actions"><button class="sh-btn" type="button" data-edit-loc="' + loc.id + '">编辑</button><button class="sh-btn" type="button" data-del-loc="' + loc.id + '" style="color:#b91c1c">删除</button></div>'
        + '</div>';
    }

    function openLocationEditor(loc) {
      var name = prompt('位置名称', loc ? loc.name : '');
      if (name === null) return;
      var type = prompt('类型（冰箱/冰柜/试剂柜/其他）', loc ? (loc.type || '冰箱') : '冰箱');
      if (type === null) return;
      var temp = prompt('温度（如 4℃ / -20℃）', loc ? (loc.temperature || '') : '');
      if (temp === null) return;
      var rowsStr = prompt('行数', loc ? loc.grid_rows : 2);
      if (rowsStr === null) return;
      var colsStr = prompt('列数', loc ? loc.grid_cols : 4);
      if (colsStr === null) return;
      var rows = parseInt(rowsStr, 10) || 2;
      var cols = parseInt(colsStr, 10) || 4;
      var payload = { name: name, type: type || '其他', temperature: temp || '', grid_rows: rows, grid_cols: cols };
      var url = loc ? '/storage/locations/' + loc.id : '/storage/locations';
      var method = loc ? 'PATCH' : 'POST';
      if (!loc) {
        payload.map_x = (allLocations.length * 30) % 600;
        payload.map_y = (allLocations.length * 40) % 400;
      }
      fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
        .then(function () { load(); });
    }

    function slotLabel(row, col) {
      return String.fromCharCode(65 + row) + '-' + String(col + 1).toString().padStart(2, '0');
    }

    function rackItemHtml(i) {
      return '<div class="rack-item" draggable="true" data-id="' + i.id + '">'
        + '<div class="rn">' + esc(i.name) + '</div>'
        + '<div class="rm">' + esc(i.quantity || '') + ' ' + esc(i.unit || '') + ' · ' + statusHtml(i.status) + '</div></div>';
    }

    function renderMap(locations, items) {
      var map = host.querySelector('#st-map');
      var unassigned = items.filter(function (i) { return !i.location_id; });
      var assigned = items.filter(function (i) { return i.location_id; });
      map.innerHTML = '<div class="storage-canvas" id="st-canvas">'
        + '<div class="hint">拖动蓝色方块可移动冰箱/柜子；点击“编辑”修改信息；拖动物品到格位可在顶部“列表”中操作</div>'
        + locations.map(function (loc) { return locationBoxHtml(loc, assigned); }).join('')
        + '<div class="canvas-loc" data-loc="" style="left:12px;top:12px;border-style:dashed;opacity:.8"><div class="cl-title">未分配<span class="cl-count">' + unassigned.length + '</span></div><div class="cl-sub">点击“编辑位置”添加新冰箱</div><div class="cl-actions"><button class="sh-btn primary" type="button" id="st-canvas-add">添加位置</button></div></div>'
        + '</div>';

      // Add location from canvas
      var addBtn = host.querySelector('#st-canvas-add');
      if (addBtn) addBtn.onclick = function () { openLocationEditor(null); };

      // Drag locations on the canvas
      Array.prototype.forEach.call(map.querySelectorAll('.canvas-loc[data-loc]'), function (box) {
        var locId = box.getAttribute('data-loc');
        if (!locId) return;
        box.addEventListener('pointerdown', function (e) {
          if (e.target.closest('button')) return;
          e.preventDefault();
          var startX = e.clientX, startY = e.clientY;
          var origLeft = parseInt(box.style.left, 10) || 0;
          var origTop = parseInt(box.style.top, 10) || 0;
          var moved = false;
          box.classList.add('dragging');
          function move(ev) {
            var nx = origLeft + (ev.clientX - startX);
            var ny = origTop + (ev.clientY - startY);
            if (!moved && Math.abs(ev.clientX - startX) + Math.abs(ev.clientY - startY) > 3) moved = true;
            box.style.left = nx + 'px';
            box.style.top = ny + 'px';
          }
          function up(ev) {
            box.classList.remove('dragging');
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', up);
            if (moved) {
              fetch('/storage/locations/' + locId, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ map_x: Math.max(0, Math.round(origLeft + (ev.clientX - startX))), map_y: Math.max(0, Math.round(origTop + (ev.clientY - startY))) })
              }).then(function () { load(); });
            }
          }
          window.addEventListener('pointermove', move);
          window.addEventListener('pointerup', up);
        });
      });

      // Edit/delete location buttons
      Array.prototype.forEach.call(map.querySelectorAll('[data-edit-loc]'), function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          var loc = allLocations.filter(function (x) { return x.id == btn.getAttribute('data-edit-loc'); })[0];
          if (loc) openLocationEditor(loc);
        };
      });
      Array.prototype.forEach.call(map.querySelectorAll('[data-del-loc]'), function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          if (!confirm('删除该位置？该位置下物品会变为未分配。')) return;
          fetch('/storage/locations/' + btn.getAttribute('data-del-loc'), { method: 'DELETE' }).then(function () { load(); });
        };
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
        allLocations = locations;
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
