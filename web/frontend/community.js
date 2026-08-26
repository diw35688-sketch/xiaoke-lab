/* 社区：浏览、发布、导入通用试剂配方与实验方案。 */
(function () {
  var host;
  var listEl;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function kindBadge(kind) {
    if (kind === 'reagent_prep') return '<span style="background:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:999px;font-size:11px">🧪 试剂配方</span>';
    if (kind === 'protocol') return '<span style="background:#f0fdf4;color:#15803d;padding:2px 8px;border-radius:999px;font-size:11px">☰ 实验方案</span>';
    return '<span style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:999px;font-size:11px">' + esc(kind) + '</span>';
  }

  function loadList(query, kind) {
    return fetch('/community?q=' + encodeURIComponent(query || '') + '&kind=' + encodeURIComponent(kind || ''))
      .then(function (r) { return r.json(); });
  }

  function render(items) {
    if (!items.length) {
      listEl.innerHTML = '<div class="com-empty">还没有社区内容。点右上角“发布到社区”，把本地配方/方案分享出去。</div>';
      return;
    }
    listEl.innerHTML = '<div class="com-grid">' + items.map(function (item) {
      var content = {};
      try { content = JSON.parse(item.content_json); } catch (e) {}
      var desc = content.purpose || (content.summary || (content.steps && content.steps.length + ' 个步骤') || '');
      return '<div class="com-card" data-id="' + item.id + '">'
        + '<div class="com-card-head">' + kindBadge(item.kind) + '<span class="com-downloads">⬇ ' + (item.downloads || 0) + '</span></div>'
        + '<div class="com-card-title">' + esc(item.title) + '</div>'
        + '<div class="com-card-desc">' + esc(desc) + '</div>'
        + '<div class="com-card-tags">' + (item.tags ? esc(item.tags) : esc(item.author ? '作者：' + item.author : '')) + '</div>'
        + '<div class="com-card-actions"><button class="sh-btn primary" data-import="' + item.id + '">导入</button>'
        + (item.author === '__me__' ? '<button class="sh-btn" data-del="' + item.id + '" style="color:#b91c1c">删除</button>' : '')
        + '</div>'
        + '</div>';
    }).join('') + '</div>';

    Array.prototype.forEach.call(listEl.querySelectorAll('[data-import]'), function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute('data-import');
        btn.textContent = '导入中…';
        fetch('/community/' + id + '/import', { method: 'POST' })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
          .then(function (res) {
            if (!res.ok) { alert(res.d.detail || '导入失败'); btn.textContent = '导入'; return; }
            alert('导入成功：' + (res.d.saved.name_zh || res.d.saved.protocol_id || ''));
            btn.textContent = '已导入';
            load();
          });
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-del]'), function (btn) {
      btn.onclick = function () {
        if (!confirm('删除这条社区内容？')) return;
        fetch('/community/' + btn.getAttribute('data-del'), { method: 'DELETE' }).then(function () { load(); });
      };
    });
  }

  function load() {
    var q = (host.querySelector('#com-search') || { value: '' }).value;
    var kind = (host.querySelector('#com-kind') || { value: '' }).value;
    loadList(q, kind).then(function (d) { render(d.items || []); });
  }

  function publishForm() {
    Promise.all([
      fetch('/reagent-prep').then(function (r) { return r.json(); }).catch(function () { return { items: [] }; }),
      fetch('/protocols').then(function (r) { return r.json(); }).catch(function () { return { items: [] }; })
    ]).then(function (res) {
      var preps = (res[0].items || []);
      var protocols = (res[1].items || []);
      var options = preps.map(function (p) {
        return '<option value="prep:' + esc(p.reagent_prep_id) + '">🧪 ' + esc(p.name_zh) + '</option>';
      }).join('') + protocols.map(function (p) {
        return '<option value="protocol:' + esc(p.protocol_id) + '">☰ ' + esc(p.title) + '</option>';
      }).join('');
      if (!options) { alert('本地还没有可发布的配方或方案，请先创建。'); return; }
      host.innerHTML = '<div class="com-publish">'
        + '<button class="sh-btn" id="com-publish-back">← 返回社区</button>'
        + '<div class="com-detail-title">发布到社区</div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">选择本地内容</label><select id="com-pick" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px">' + options + '</select></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">标题</label><input id="com-title" placeholder="不填则用原名" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">作者</label><input id="com-author" placeholder="你的名字/课题组" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">标签</label><input id="com-tags" placeholder="用逗号分隔，如 植物,1/2MS,母液" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:12px"><button class="sh-btn primary" id="com-publish-save">发布</button><span id="com-publish-msg" style="font-size:12px;color:#64748b;margin-left:8px"></span></div>'
        + '</div>';
      host.querySelector('#com-publish-back').onclick = init;
      host.querySelector('#com-publish-save').onclick = function () {
        var pick = host.querySelector('#com-pick').value;
        if (!pick) return;
        var parts = pick.split(':');
        var kind = parts[0] === 'prep' ? 'reagent_prep' : 'protocol';
        var id = parts.slice(1).join(':');
        var selected = (kind === 'reagent_prep' ? preps : protocols).filter(function (x) {
          return (kind === 'reagent_prep' ? x.reagent_prep_id : x.protocol_id) === id;
        })[0];
        if (!selected) { host.querySelector('#com-publish-msg').textContent = '没找到所选内容'; return; }
        var title = host.querySelector('#com-title').value.trim() || (selected.name_zh || selected.title || '');
        fetch('/community', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            kind: kind,
            title: title,
            content: selected,
            author: host.querySelector('#com-author').value.trim(),
            tags: host.querySelector('#com-tags').value.trim()
          })
        }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (res) {
          if (!res.ok) { host.querySelector('#com-publish-msg').textContent = res.d.detail || '发布失败'; return; }
          alert('发布成功');
          init();
        });
      };
    });
  }

  function ensureStyles() {
    if (document.getElementById('community-style')) return;
    var style = document.createElement('style');
    style.id = 'community-style';
    style.textContent = [
      '.com-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:10px 12px;margin-bottom:12px}',
      '.com-toolbar input,.com-toolbar select{padding:8px 10px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.com-toolbar input{flex:1;min-width:160px}',
      '.com-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}',
      '.com-card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px;box-shadow:0 2px 8px rgba(15,23,42,.04)}',
      '.com-card:hover{box-shadow:0 6px 18px rgba(15,23,42,.08)}',
      '.com-card-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}',
      '.com-card-title{font-weight:700;font-size:15px;color:#0f172a;line-height:1.35}',
      '.com-card-desc{color:#64748b;font-size:12px;margin-top:6px;min-height:2em}',
      '.com-card-tags{color:#94a3b8;font-size:11px;margin-top:6px}',
      '.com-card-actions{display:flex;gap:6px;margin-top:10px}',
      '.com-card-actions .sh-btn{padding:4px 10px;font-size:12px}',
      '.com-empty{color:#94a3b8;font-size:13px;margin:20px 0}',
      '.com-publish{max-width:760px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:18px}',
      '.com-detail-title{font-size:20px;font-weight:700;color:#0f172a;margin:12px 0 2px}',
      '@media(max-width:900px){.com-grid{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function init() {
    ensureStyles();
    host.innerHTML = '<div class="com-toolbar">'
      + '<input id="com-search" type="search" placeholder="搜索标题 / 作者 / 标签…">'
      + '<select id="com-kind"><option value="">全部类型</option><option value="reagent_prep">试剂配方</option><option value="protocol">实验方案</option></select>'
      + '<button class="sh-btn" id="com-publish">发布到社区</button>'
      + '</div><div id="com-list"></div>';
    listEl = host.querySelector('#com-list');
    var search = host.querySelector('#com-search');
    var kind = host.querySelector('#com-kind');
    search.addEventListener('input', debounce(load, 250));
    kind.addEventListener('change', load);
    host.querySelector('#com-publish').onclick = publishForm;
    load();
  }

  var timer = null;
  function debounce(fn, ms) {
    return function () { clearTimeout(timer); timer = setTimeout(fn, ms); };
  }

  window.shellRegisterView('community', function (container) {
    host = container;
    init();
  });
})();
