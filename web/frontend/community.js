/* 社区：远程模板市场。本地作为前端，用户浏览/预览/导入/发布自己的试剂配方或实验方案模板。 */
(function () {
  var REMOTE_BASE = '/community-proxy';
  var host, listEl, token = localStorage.getItem('community_remote_token') || '';
  var currentUser = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function api(path, opts) {
    opts = opts || {};
    if (window.logAction) window.logAction('community_api', { path: path, method: opts.method || 'GET' });
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) opts.headers.Authorization = 'Bearer ' + token;
    return fetch(REMOTE_BASE + path, opts).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).catch(function () { return { ok: false, d: { detail: '连接远程社区失败，请检查网络' } }; });
  }

  function kindBadge(kind) {
    if (kind === 'reagent_prep') return '<span class="ch-badge ch-badge-prep">🧪 试剂配方</span>';
    if (kind === 'protocol') return '<span class="ch-badge ch-badge-protocol">☰ 实验方案</span>';
    return '<span class="ch-badge">' + esc(kind) + '</span>';
  }

  function initials(name) {
    return (name || '?').slice(0, 1).toUpperCase();
  }

  function userLabel() {
    var box = host.querySelector('#com-user-box');
    if (!token) {
      box.innerHTML = '<button class="ch-btn" id="com-login-btn">登录 / 注册</button>';
      box.querySelector('#com-login-btn').onclick = openAuth;
      return;
    }
    api('/auth/me').then(function (res) {
      if (!res.ok) { token = ''; localStorage.removeItem('community_remote_token'); currentUser = null; userLabel(); return; }
      currentUser = res.d.user;
      box.innerHTML = '<span class="ch-user">' + esc(res.d.user.username || '') + (res.d.user.role === 'admin' ? ' <span class="ch-crown">👑</span>' : '') + '</span> '
        + '<button class="ch-btn ghost" id="com-logout">退出</button>';
      var adminBtn = host.querySelector('#com-admin-btn');
      if (adminBtn) adminBtn.style.display = res.d.user.role === 'admin' ? '' : 'none';
      box.querySelector('#com-logout').onclick = function () {
        token = ''; localStorage.removeItem('community_remote_token'); currentUser = null;
        var adminBtn = host.querySelector('#com-admin-btn');
        if (adminBtn) adminBtn.style.display = 'none';
        userLabel(); load();
      };
    });
  }

  function openAuth() {
    var box = host.querySelector('#com-auth-box');
    box.style.display = '';
    box.innerHTML = '<div class="ch-modal-card"><div class="ch-modal-title">登录 / 注册社区账号</div>'
      + '<div><label class="ch-label">用户名</label><input id="com-user" class="ch-input" autocomplete="username"></div>'
      + '<div style="margin-top:8px"><label class="ch-label">密码</label><input id="com-pass" class="ch-input" type="password" autocomplete="current-password"></div>'
      + '<div id="com-auth-msg" class="ch-msg"></div>'
      + '<div style="margin-top:12px;display:flex;gap:8px"><button class="ch-btn primary" id="com-auth-login">登录</button><button class="ch-btn" id="com-auth-reg">注册</button><button class="ch-btn ghost" id="com-auth-close">关闭</button></div>'
      + '</div>';
    host.querySelector('#com-auth-close').onclick = function () { box.style.display = 'none'; };
    host.querySelector('#com-auth-login').onclick = function () {
      api('/auth/login', { method: 'POST', body: JSON.stringify({ username: host.querySelector('#com-user').value.trim(), password: host.querySelector('#com-pass').value }) })
        .then(function (res) {
          if (!res.ok) { host.querySelector('#com-auth-msg').textContent = res.d.detail || '登录失败'; return; }
          token = res.d.token; localStorage.setItem('community_remote_token', token);
          box.style.display = 'none'; userLabel(); load();
        });
    };
    host.querySelector('#com-auth-reg').onclick = function () {
      api('/auth/register', { method: 'POST', body: JSON.stringify({ username: host.querySelector('#com-user').value.trim(), password: host.querySelector('#com-pass').value }) })
        .then(function (res) {
          if (!res.ok) { host.querySelector('#com-auth-msg').textContent = res.d.detail || '注册失败'; return; }
          token = res.d.token; localStorage.setItem('community_remote_token', token);
          box.style.display = 'none'; userLabel(); load();
        });
    };
  }

  function load() {
    var q = (host.querySelector('#com-search') || { value: '' }).value;
    var kind = (host.querySelector('#com-kind') || { value: '' }).value;
    api('/community?q=' + encodeURIComponent(q) + '&kind=' + encodeURIComponent(kind)).then(function (res) {
      if (!res.ok) { listEl.innerHTML = '<div class="com-empty">' + esc(res.d.detail || '加载失败') + '</div>'; return; }
      render(res.d.items || []);
    });
  }

  function stepHtml(content) {
    if (!content || !Array.isArray(content.steps)) return '';
    return '<ol class="ch-steps">' + content.steps.slice(0, 8).map(function (s) {
      return '<li>' + esc(s) + '</li>';
    }).join('') + '</ol>';
  }

  function detailModal(item) {
    var c = item.content || {};
    var meta = [];
    if (c.target_concentration) meta.push('目标 ' + esc(c.target_concentration));
    if (c.target_volume) meta.push('体积 ' + esc(c.target_volume));
    if (c.solvent) meta.push('溶剂 ' + esc(c.solvent));
    if (c.storage_condition) meta.push('保存 ' + esc(c.storage_condition));
    var body = '<div class="ch-modal">'
      + '<div class="ch-modal-head"><div>' + kindBadge(item.kind) + '<div class="ch-detail-title">' + esc(item.title) + '</div>'
      + '<div class="ch-meta-small">' + esc(item.author || '') + ' · ' + (item.downloads || 0) + ' 次导入 · ' + (item.likes || 0) + ' 点赞' + '</div></div>'
      + '<button class="ch-btn ghost" id="ch-detail-close">✕</button></div>'
      + (c.purpose ? '<div class="ch-desc">' + esc(c.purpose) + '</div>' : '')
      + (meta.length ? '<div class="ch-meta">' + meta.join(' · ') + '</div>' : '')
      + (stepHtml(c) ? '<div class="ch-section">模板步骤</div>' + stepHtml(c) : '')
      + '<div style="margin-top:14px;display:flex;gap:8px"><button class="ch-btn primary" id="ch-detail-import">导入到本地</button><button class="ch-btn" id="ch-detail-like">点赞</button>'
      + (currentUser && currentUser.role === 'admin' ? '<button class="ch-btn" id="ch-detail-del" style="color:#b91c1c">删除</button>' : '')
      + '</div></div>';
    var mask = document.createElement('div');
    mask.className = 'ch-modal-mask';
    mask.innerHTML = body;
    document.body.appendChild(mask);
    mask.onclick = function (e) { if (e.target === mask) mask.remove(); };
    mask.querySelector('#ch-detail-close').onclick = function () { mask.remove(); };
    mask.querySelector('#ch-detail-import').onclick = function () {
      importItem(item, mask.querySelector('#ch-detail-import'));
    };
    mask.querySelector('#ch-detail-like').onclick = function () {
      api('/community/' + item.id + '/like', { method: 'POST', body: '{}' }).then(function () { load(); });
    };
    var delBtn = mask.querySelector('#ch-detail-del');
    if (delBtn) delBtn.onclick = function () {
      if (!confirm('确定删除？')) return;
      api('/community/' + item.id, { method: 'DELETE' }).then(function () { mask.remove(); load(); });
    };
  }

  function render(items) {
    if (!items.length) {
      listEl.innerHTML = '<div class="com-empty">还没有公开模板。登录后发布一个试试。</div>';
      return;
    }
    listEl.innerHTML = '<div class="ch-grid">' + items.map(function (item) {
      var c = item.content || {};
      var desc = c.purpose || (c.summary || ((c.steps || []).length + ' 个步骤') || '');
      var mine = false;
      try { mine = item.author === JSON.parse(atob((token.split('.')[1] || '').replace(/-/g, '+').replace(/_/g, '/'))).username; } catch (e) {}
      return '<div class="ch-card" data-id="' + item.id + '">'
        + '<div class="ch-card-top">' + kindBadge(item.kind)
        + '<span class="ch-avatar" title="' + esc(item.author || '') + '">' + initials(item.author || '?') + '</span></div>'
        + '<div class="ch-card-title">' + esc(item.title) + '</div>'
        + '<div class="ch-card-desc">' + esc(desc) + '</div>'
        + '<div class="ch-card-tags">' + (item.tags ? esc(item.tags).split(',').slice(0,3).map(function(t){return '<span class="ch-tag">'+esc(t.trim())+'</span>';}).join('') : esc(item.author || '')) + '</div>'
        + '<div class="ch-card-foot"><span class="ch-stat">⬇ ' + (item.downloads || 0) + '</span><span class="ch-stat">♥ ' + (item.likes || 0) + '</span>'
        + '<button class="ch-btn small primary" data-import="' + item.id + '">导入</button>'
        + (mine ? '<button class="ch-btn small ghost" data-del="' + item.id + '" style="color:#b91c1c">删除</button>' : '')
        + '</div></div>';
    }).join('') + '</div>';

    Array.prototype.forEach.call(listEl.querySelectorAll('.ch-card'), function (card) {
      card.onclick = function (e) {
        if (e.target.closest('[data-import]') || e.target.closest('[data-del]')) return;
        var item = items.filter(function (x) { return x.id == card.getAttribute('data-id'); })[0];
        if (item) detailModal(item);
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-import]'), function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var item = items.filter(function (x) { return x.id == btn.getAttribute('data-import'); })[0];
        importItem(item, btn);
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-del]'), function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        if (!confirm('确定删除？')) return;
        api('/community/' + btn.getAttribute('data-del'), { method: 'DELETE' }).then(function () { load(); });
      };
    });
  }

  function importItem(item, btn) {
    var old = btn.textContent;
    btn.textContent = '导入中…';
    api('/community/' + item.id + '/download').then(function (res) {
      if (!res.ok) { alert(res.d.detail || '下载失败'); btn.textContent = old; return; }
      return importToLocal(res.d).then(function () {
        alert('已导入到本地');
        btn.textContent = '已导入';
        load();
      }).catch(function (e) {
        alert('导入失败：' + e.message);
        btn.textContent = old;
      });
    });
  }

  function importToLocal(entry) {
    var content = entry.content || entry;
    if (entry.kind === 'reagent_prep') {
      return fetch('/reagent-prep/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reagent_preps: [content] }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) { if (!res.ok) throw new Error(res.d.detail || '试剂配置导入失败'); return true; });
    }
    if (entry.kind === 'protocol') {
      return fetch('/protocols/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ protocols: [content] }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) { if (!res.ok) throw new Error(res.d.detail || '方案导入失败'); return true; });
    }
    return Promise.reject(new Error('未知类型'));
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
      host.innerHTML = '<div class="com-publish"><button class="sh-btn" id="com-publish-back">← 返回社区</button>'
        + '<div class="com-detail-title">发布模板到社区</div>'
        + '<div style="margin-top:10px"><label class="ch-label">选择本地模板</label><select id="com-pick" class="ch-input">' + options + '</select></div>'
        + '<div style="margin-top:10px"><label class="ch-label">标题</label><input id="com-title" class="ch-input" placeholder="不填则用原名"></div>'
        + '<div style="margin-top:10px"><label class="ch-label">作者</label><input id="com-author" class="ch-input" placeholder="留空用登录名"></div>'
        + '<div style="margin-top:10px"><label class="ch-label">标签</label><input id="com-tags" class="ch-input" placeholder="植物,1/2MS,母液"></div>'
        + '<div style="margin-top:12px"><button class="ch-btn primary" id="com-publish-save">发布</button><span id="com-publish-msg" style="font-size:12px;color:#64748b;margin-left:8px"></span></div>'
        + '</div>';
      host.querySelector('#com-publish-back').onclick = init;
      host.querySelector('#com-publish-save').onclick = function () {
        if (!token) { openAuth(); return; }
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
        api('/community', {
          method: 'POST',
          body: JSON.stringify({
            kind: kind,
            title: title,
            content: selected,
            author: host.querySelector('#com-author').value.trim(),
            tags: host.querySelector('#com-tags').value.trim()
          })
        }).then(function (res) {
          if (!res.ok) { host.querySelector('#com-publish-msg').textContent = res.d.detail || '发布失败'; return; }
          alert('发布成功' + (currentUser && currentUser.role === 'admin' ? '' : '，等待管理员审核'));
          init();
        });
      };
    });
  }

  function showAdmin() {
    if (!currentUser || currentUser.role !== 'admin') { alert('需要管理员权限'); return; }
    api('/admin/entries').then(function (res) {
      if (!res.ok) { alert(res.d.detail || '加载失败'); return; }
      var items = res.d.items || [];
      listEl.innerHTML = items.map(function (item) {
        var statusLabel = item.status === 'published' ? '<span style="color:#15803d">已发布</span>' : (item.status === 'rejected' ? '<span style="color:#b91c1c">已拒绝</span>' : '<span style="color:#b45309">待审核</span>');
        return '<div class="ch-card"><div class="ch-card-top">' + kindBadge(item.kind) + statusLabel + '</div>'
          + '<div class="ch-card-title">' + esc(item.title) + ' <span style="font-size:11px;color:#94a3b8">@' + esc(item.author || '') + '</span></div>'
          + '<div class="ch-card-actions">'
          + (item.status !== 'published' ? '<button class="ch-btn small primary" data-approve="' + item.id + '">通过</button>' : '<button class="ch-btn small" data-reject="' + item.id + '">下架</button>')
          + '<button class="ch-btn small" data-del="' + item.id + '" style="color:#b91c1c">删除</button>'
          + '</div></div>';
      }).join('') || '<div class="com-empty">没有内容</div>';
      Array.prototype.forEach.call(listEl.querySelectorAll('[data-approve]'), function (btn) {
        btn.onclick = function () { api('/admin/entries/' + btn.getAttribute('data-approve') + '/approve', { method: 'POST', body: '{}' }).then(function () { showAdmin(); }); };
      });
      Array.prototype.forEach.call(listEl.querySelectorAll('[data-reject]'), function (btn) {
        btn.onclick = function () { api('/admin/entries/' + btn.getAttribute('data-reject') + '/reject', { method: 'POST', body: '{}' }).then(function () { showAdmin(); }); };
      });
      Array.prototype.forEach.call(listEl.querySelectorAll('[data-del]'), function (btn) {
        btn.onclick = function () { if (confirm('确定删除？')) api('/community/' + btn.getAttribute('data-del'), { method: 'DELETE' }).then(function () { showAdmin(); }); };
      });
    });
  }

  function ensureStyles() {
    if (document.getElementById('community-style')) return;
    var style = document.createElement('style');
    style.id = 'community-style';
    style.textContent = [
      '.com-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:12px;margin-bottom:12px}',
      '.com-toolbar input,.com-toolbar select{padding:9px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.com-toolbar input{flex:1;min-width:160px}',
      '.ch-badge{font-size:11px;padding:2px 8px;border-radius:999px;background:#f1f5f9;color:#475569}',
      '.ch-badge-prep{background:#eff6ff;color:#1d4ed8}',
      '.ch-badge-protocol{background:#f0fdf4;color:#15803d}',
      '.ch-btn{padding:8px 14px;border:1px solid #cbd5e1;background:#fff;border-radius:10px;cursor:pointer;font-size:13px;font-family:inherit}',
      '.ch-btn.primary{background:#2563eb;border-color:#2563eb;color:#fff}',
      '.ch-btn.ghost{background:#f8fafc}',
      '.ch-btn.small{padding:4px 10px;font-size:12px}',
      '.ch-user{font-size:13px;color:#334155;font-weight:600}',
      '.ch-crown{color:#b45309}',
      '.ch-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}',
      '.ch-card{background:#fff;border:1px solid #e5e8f0;border-radius:16px;padding:16px;box-shadow:0 2px 10px rgba(15,23,42,.04);cursor:pointer;transition:box-shadow .15s,transform .15s}',
      '.ch-card:hover{box-shadow:0 10px 26px rgba(15,23,42,.1);transform:translateY(-2px)}',
      '.ch-card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}',
      '.ch-avatar{width:28px;height:28px;border-radius:50%;background:#e0e7ff;color:#3730a3;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}',
      '.ch-card-title{font-weight:700;font-size:15px;line-height:1.35;color:#0f172a}',
      '.ch-card-desc{color:#64748b;font-size:13px;margin:6px 0;min-height:2em;line-height:1.5}',
      '.ch-card-tags{color:#94a3b8;font-size:11px;margin-bottom:8px}',
      '.ch-tag{background:#f1f5f9;color:#475569;border-radius:999px;padding:2px 7px;margin-right:4px}',
      '.ch-card-foot{display:flex;gap:6px;align-items:center;margin-top:8px}',
      '.ch-stat{color:#94a3b8;font-size:12px;margin-right:4px}',
      '.ch-card-actions{display:flex;gap:6px;margin-top:10px}',
      '.ch-modal-mask{position:fixed;inset:0;background:rgba(15,23,42,.5);display:flex;align-items:flex-start;justify-content:center;z-index:9999;padding:40px 16px}',
      '.ch-modal{background:#fff;border-radius:18px;padding:24px;max-width:720px;width:100%;max-height:88vh;overflow:auto;box-shadow:0 24px 60px rgba(15,23,42,.28)}',
      '.ch-modal-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}',
      '.ch-detail-title{font-size:20px;font-weight:700;color:#0f172a;margin:10px 0 4px}',
      '.ch-meta-small{color:#94a3b8;font-size:12px}',
      '.ch-desc{color:#334155;font-size:14px;margin:12px 0;line-height:1.7}',
      '.ch-meta{background:#f8fafc;border-radius:10px;padding:10px 12px;font-size:13px;color:#475569;margin-bottom:10px}',
      '.ch-section{font-weight:700;color:#0f172a;margin:14px 0 6px}',
      '.ch-steps{margin:0;padding-left:22px;color:#475569;font-size:13px;line-height:1.9}',
      '.ch-modal-card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px 18px;max-width:420px}',
      '.ch-modal-title{font-size:16px;font-weight:700;color:#0f172a;margin-bottom:10px}',
      '.ch-label{display:block;font-size:12px;color:#475569;margin-bottom:4px}',
      '.ch-input{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;font-family:inherit}',
      '.ch-msg{font-size:12px;color:#b91c1c;margin-top:6px}',
      '.com-publish{max-width:760px;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:18px}',
      '.com-detail-title{font-size:20px;font-weight:700;color:#0f172a;margin:12px 0 2px}',
      '.com-empty{color:#94a3b8;font-size:13px;margin:20px 0}',
      '@media(max-width:900px){.ch-grid{grid-template-columns:1fr}}',
      ''
    ].join('\n');
    document.head.appendChild(style);
  }

  function init() {
    ensureStyles();
    host.innerHTML = '<div class="com-toolbar">'
      + '<span style="font-weight:800;font-size:15px;color:#0f172a">🌐 实验模板社区</span>'
      + '<input id="com-search" type="search" placeholder="搜索模板 / 作者 / 标签…">'
      + '<select id="com-kind"><option value="">全部模板</option><option value="reagent_prep">🧪 试剂配方</option><option value="protocol">☰ 实验方案</option></select>'
      + '<button class="ch-btn primary" id="com-publish">发布模板</button>'
      + '<button class="ch-btn" id="com-admin-btn" style="display:none">管理审核</button>'
      + '<span id="com-user-box" style="margin-left:auto;display:flex;align-items:center;gap:8px"></span>'
      + '</div><div id="com-auth-box" style="display:none;margin-bottom:10px"></div><div id="com-list"></div>';
    listEl = host.querySelector('#com-list');
    var search = host.querySelector('#com-search');
    var kind = host.querySelector('#com-kind');
    search.addEventListener('input', debounce(load, 250));
    kind.addEventListener('change', load);
    host.querySelector('#com-publish').onclick = function () {
      if (!token) { openAuth(); return; }
      publishForm();
    };
    host.querySelector('#com-admin-btn').onclick = showAdmin;
    userLabel();
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
