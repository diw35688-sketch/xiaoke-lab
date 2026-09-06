// 知识库：表格上传 + 全文检索
// 功能：
//   1. 上传 Excel/CSV → 自动导入 → 建索引
//   2. 卡片展示已上传的表格（名称、行数、列数）
//   3. 搜索框：输入关键词 → 跨所有表格全文匹配
//   4. 点击卡片 → 查看表格详情和原始数据
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function api(path, method, payload) {
    var opts = { method: method || 'GET' };
    if (payload) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(payload);
    }
    return fetch(path, opts).then(function (r) { return r.json(); });
  }
  function uploadApi(formData) {
    return fetch('/kb/upload', { method: 'POST', body: formData }).then(function (r) { return r.json(); });
  }

  function ensureStyles() {
    if (document.getElementById('kb-style')) return;
    var style = document.createElement('style');
    style.id = 'kb-style';
    style.textContent = [
      '.kb-page{max-width:900px;margin:0 auto}',
      '.kb-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:12px;margin-bottom:12px}',
      '.kb-toolbar input[type=search]{flex:1;min-width:200px;padding:9px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.kb-toolbar input[type=search]:focus{outline:2px solid rgba(59,103,232,.25);border-color:#3b67e8}',
      '.kb-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-top:12px}',
      '.kb-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;cursor:pointer;transition:border-color .15s,box-shadow .15s;position:relative}',
      '.kb-card:hover{border-color:#3b67e8;box-shadow:0 4px 12px rgba(59,103,232,.08)}',
      '.kb-card-name{font-weight:600;color:#0f172a;font-size:14px;margin-bottom:4px}',
      '.kb-card-meta{color:#64748b;font-size:12px;line-height:1.6}',
      '.kb-card-cols{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}',
      '.kb-col-tag{font-size:10px;background:#f1f5f9;color:#475569;padding:2px 7px;border-radius:5px}',
      '.kb-results{margin-top:16px}',
      '.kb-result-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}',
      '.kb-result-table th{background:#f8fafc;color:#475569;padding:6px 8px;text-align:left;border-bottom:2px solid #e2e8f0;white-space:nowrap}',
      '.kb-result-table td{padding:6px 8px;border-bottom:1px solid #f1f5f9;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.kb-result-table tr:hover{background:#f8fafc}',
      '.kb-result-source{font-size:11px;color:#3b67e8;font-weight:600;margin-bottom:2px}',
      '.kb-empty{color:#94a3b8;font-size:13px;padding:40px 0;text-align:center}',
      '.kb-upload-hint{font-size:12px;color:#64748b;margin-top:8px}',
      '@media(max-width:768px){.kb-grid{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function render(host) {
    ensureStyles();
    var searchTimer = null;

    host.innerHTML = '<div class="kb-page">'
      + '<div class="kb-toolbar">'
      + '<span style="font-weight:700;font-size:14px;color:#0f172a">📚 知识库</span>'
      + '<input type="search" id="kb-search" placeholder="搜索引物、基因、功能…" autocomplete="off" spellcheck="false" name="noname-kb-search">'
      + '<button class="sh-btn primary" id="kb-upload-btn">上传表格</button>'
      + '<input type="file" id="kb-file" accept=".xlsx,.xls,.csv" style="display:none">'
      + '</div>'
      + '<div class="kb-upload-hint" id="kb-upload-msg">支持 Excel(.xlsx) 和 CSV 格式。第一行为表头，如：引物名称、靶基因、序列、Tm值…</div>'
      + '<div id="kb-results"></div>'
      + '<div id="kb-grid-section">'
      + '<div style="font-size:13px;color:#475569;margin-top:16px;font-weight:600">已上传的表格</div>'
      + '<div class="kb-grid" id="kb-grid"></div>'
      + '</div>'
      + '</div>';

    var grid = host.querySelector('#kb-grid');
    var results = host.querySelector('#kb-results');

    // ---- 加载表格卡片 ----
    function loadTables() {
      api('/kb/tables').then(function (d) {
        if (!d.tables || d.tables.length === 0) {
          grid.innerHTML = '<div class="kb-empty">还没有上传表格。点击「上传表格」导入实验室共享的引物表、试剂表等。</div>';
          return;
        }
        grid.innerHTML = d.tables.map(function (t) {
          var colTags = (t.columns || []).slice(0, 6).map(function (c) {
            return '<span class="kb-col-tag">' + esc(c) + '</span>';
          }).join('');
          var extra = t.columns.length > 6 ? '<span class="kb-col-tag">+' + (t.columns.length - 6) + '</span>' : '';
          return '<div class="kb-card" data-table-id="' + esc(t.id) + '">'
            + '<div class="kb-card-name">' + esc(t.name) + '</div>'
            + (t.description ? '<div class="kb-card-meta">' + esc(t.description) + '</div>' : '')
            + '<div class="kb-card-meta">' + (t.row_count || 0) + ' 行 · ' + (t.columns.length) + ' 列 · ' + esc(t.file_name) + '</div>'
            + '<div class="kb-card-cols">' + colTags + extra + '</div>'
            + '<div style="margin-top:10px;display:flex;gap:8px">'
            + '<button class="sh-btn" style="padding:3px 9px;font-size:12px" data-view-table="' + esc(t.id) + '">查看</button>'
            + '<button class="sh-btn" style="padding:3px 9px;font-size:12px;color:#b91c1c" data-del-table="' + esc(t.id) + '" data-name="' + esc(t.name) + '">删除</button>'
            + '</div></div>';
        }).join('');

        // 绑定卡片点击
        Array.prototype.forEach.call(grid.querySelectorAll('[data-view-table]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            showTableDetail(host, btn.getAttribute('data-view-table'));
          };
        });
        Array.prototype.forEach.call(grid.querySelectorAll('[data-del-table]'), function (btn) {
          btn.onclick = function (e) {
            e.stopPropagation();
            var id = btn.getAttribute('data-del-table');
            var name = btn.getAttribute('data-name');
            if (!confirm('确认删除表格「' + name + '」？所有数据将被移除。')) return;
            api('/kb/tables/' + encodeURIComponent(id), 'DELETE').then(function () {
              loadTables();
            });
          };
        });
      }).catch(function () {
        grid.innerHTML = '<div class="kb-empty">加载失败，请刷新重试。</div>';
      });
    }
    loadTables();

    // ---- 搜索 ----
    function doSearch(q) {
      if (!q || !q.trim()) {
        results.innerHTML = '';
        host.querySelector('#kb-grid-section').style.display = '';
        return;
      }
      results.innerHTML = '<div style="color:#94a3b8;font-size:13px;padding:12px 0">搜索中…</div>';
      api('/kb/search?q=' + encodeURIComponent(q)).then(function (d) {
        host.querySelector('#kb-grid-section').style.display = 'none';
        if (!d.count) {
          results.innerHTML = '<div style="margin-top:12px"><div style="color:#94a3b8;font-size:13px">没有找到匹配「' + esc(q) + '」的结果。</div></div>';
          return;
        }
        // 按表格分组
        var groups = {};
        d.results.forEach(function (r) {
          var key = r.table_id;
          if (!groups[key]) groups[key] = { name: r.table_name, columns: r.columns, rows: [] };
          groups[key].rows.push(r.data);
        });

        var html = '<div style="margin-top:12px;font-size:13px;color:#475569">找到 ' + d.count + ' 条匹配「' + esc(q) + '」的结果</div>';
        Object.keys(groups).forEach(function (key) {
          var g = groups[key];
          var cols = g.columns || Object.keys(g.rows[0] || {});
          var headers = cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('');
          var bodyHtml = g.rows.map(function (row) {
            return '<tr>' + cols.map(function (c) {
              return '<td title="' + esc(row[c] || '') + '">' + esc(row[c] || '') + '</td>';
            }).join('') + '</tr>';
          }).join('');
          html += '<div style="margin-top:14px">'
            + '<div class="kb-result-source">📋 ' + esc(g.name) + ' (' + g.rows.length + ' 条)</div>'
            + '<div style="overflow-x:auto"><table class="kb-result-table"><thead><tr>' + headers + '</tr></thead><tbody>' + bodyHtml + '</tbody></table></div>'
            + '</div>';
        });
        results.innerHTML = html;
      }).catch(function () {
        results.innerHTML = '<div class="kb-empty">搜索失败，请重试。</div>';
      });
    }

    var searchInput = host.querySelector('#kb-search');
    searchInput.oninput = function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () { doSearch(searchInput.value); }, 300);
    };

    // ---- 上传 ----
    var fileInput = host.querySelector('#kb-file');
    host.querySelector('#kb-upload-btn').onclick = function () { fileInput.click(); };
    fileInput.onchange = function () {
      var file = fileInput.files[0];
      if (!file) return;
      var hint = host.querySelector('#kb-upload-msg');
      hint.textContent = '正在导入 ' + file.name + '…';

      // 弹出命名对话框
      var name = prompt('给这个表格起个名字：', file.name.replace(/\.(xlsx|xls|csv)$/i, ''));
      if (name === null) { fileInput.value = ''; hint.textContent = '已取消'; return; }

      var fd = new FormData();
      fd.append('file', file);
      fd.append('name', name);
      fd.append('description', '');

      uploadApi(fd).then(function (d) {
        if (d.ok) {
          hint.innerHTML = '✓ 导入成功：<b>' + esc(d.name) + '</b>（' + d.row_count + ' 行 × ' + d.columns.length + ' 列）';
          fileInput.value = '';
          loadTables();
        } else {
          hint.innerHTML = '<span style="color:#dc2626">✗ ' + esc(d.detail || '导入失败') + '</span>';
          fileInput.value = '';
        }
      }).catch(function (e) {
        hint.innerHTML = '<span style="color:#dc2626">✗ 上传失败：' + esc(e.message) + '</span>';
        fileInput.value = '';
      });
    };
  }

  function showTableDetail(host, tableId) {
    var grid = host.querySelector('#kb-grid-section');
    api('/kb/tables/' + encodeURIComponent(tableId) + '/rows?limit=200').then(function (d) {
      var t = d.table;
      var rows = d.rows || [];
      var cols = t.columns || Object.keys(rows[0] || {});
      var headers = cols.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('');
      var bodyHtml = rows.map(function (row) {
        return '<tr>' + cols.map(function (c) {
          return '<td title="' + esc(row[c] || '') + '">' + esc(row[c] || '') + '</td>';
        }).join('') + '</tr>';
      }).join('');

      grid.innerHTML = '<div style="margin-top:8px">'
        + '<button class="sh-btn" id="kb-back">← 返回</button>'
        + '<span style="font-size:14px;font-weight:700;color:#0f172a;margin-left:10px">📋 ' + esc(t.name) + '</span>'
        + (t.description ? '<span style="color:#64748b;font-size:12px;margin-left:8px">' + esc(t.description) + '</span>' : '')
        + '<span style="color:#64748b;font-size:12px;margin-left:8px">' + rows.length + '/' + d.total + ' 行</span>'
        + '</div>'
        + '<div style="overflow-x:auto;margin-top:10px"><table class="kb-result-table"><thead><tr>' + headers + '</tr></thead><tbody>' + bodyHtml + '</tbody></table></div>';

      var back = host.querySelector('#kb-back');
      if (back) back.onclick = function () {
        // 重新渲染整个页面
        window.shellShow('kb');
      };
    }).catch(function () {
      grid.innerHTML = '<div class="kb-empty">加载表格详情失败。</div>';
    });
  }

  window.shellRegisterView('kb', render);
})();
