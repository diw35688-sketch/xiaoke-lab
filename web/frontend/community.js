/* 社区：远程开放式社区。本地页只做前端交互，数据/账号在远程服务器。 */
(function () {
  var REMOTE_BASE = localStorage.getItem('community_remote_base') || 'http://124.221.234.222:3000/api';
  var host, listEl, token = localStorage.getItem('community_remote_token') || '';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) opts.headers.Authorization = 'Bearer ' + token;
    return fetch(REMOTE_BASE + path, opts).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).catch(function () { return { ok: false, d: { detail: '连接远程社区失败，请检查网络' } }; });
  }

  function kindBadge(kind) {
    if (kind === 'reagent_prep') return '<span style="background:#eff6ff;color:#1d4ed8;padding:2px 8px;border-radius:999px;font-size:11px">🧪 试剂配方</span>';
    if (kind === 'protocol') return '<span style="background:#f0fdf4;color:#15803d;padding:2px 8px;border-radius:999px;font-size:11px">☰ 实验方案</span>';
    return '<span style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:999px;font-size:11px">' + esc(kind) + '</span>';
  }

  function userLabel() {
    var box = host.querySelector('#com-user-box');
    if (!token) {
      box.innerHTML = '<button class="sh-btn" id="com-login-btn">登录 / 注册</button>';
      box.querySelector('#com-login-btn').onclick = openAuth;
      return;
    }
    api('/auth/me').then(function (res) {
      if (!res.ok) { token = ''; localStorage.removeItem('community_remote_token'); userLabel(); return; }
      box.innerHTML = '<span style="font-size:13px;color:#334155">' + esc(res.d.user.username) + '</span> '
        + '<button class="sh-btn" id="com-logout">退出</button>';
      box.querySelector('#com-logout').onclick = function () {
        token = ''; localStorage.removeItem('community_remote_token'); userLabel(); load();
      };
    });
  }

  function openAuth() {
    var box = host.querySelector('#com-auth-box');
    box.style.display = '';
    box.innerHTML = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:16px 18px;max-width:420px">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:10px">登录 / 注册</div>'
      + '<div><label style="font-size:12px;color:#475569">用户名</label><input id="com-user" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
      + '<div style="margin-top:8px"><label style="font-size:12px;color:#475569">密码</label><input id="com-pass" type="password" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
      + '<div id="com-auth-msg" style="font-size:12px;color:#b91c1c;margin-top:6px"></div>'
      + '<div style="margin-top:12px;display:flex;gap:8px"><button class="sh-btn primary" id="com-auth-login">登录</button><button class="sh-btn" id="com-auth-reg">注册</button><button class="sh-btn" id="com-auth-close">关闭</button></div>'
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

  function render(items) {
    if (!items.length) {
      listEl.innerHTML = '<div class="com-empty">社区还没有内容。登录后点“发布到社区”，把本地配方/方案分享出去。</div>';
      return;
    }
    listEl.innerHTML = '<div class="com-grid">' + items.map(function (item) {
      var c = item.content || {};
      var desc = c.purpose || (c.summary || ((c.steps || []).length + ' 个步骤') || '');
      var mine = false;
      try { mine = item.author === JSON.parse(atob((token.split('.')[1] || '').replace(/-/g, '+').replace(/_/g, '/'))).username; } catch (e) {}
      return '<div class="com-card" data-id="' + item.id + '">'
        + '<div class="com-card-head">' + kindBadge(item.kind) + '<span class="com-downloads">⬇ ' + (item.downloads || 0) + ' · ♥ ' + (item.likes || 0) + '</span></div>'
        + '<div class="com-card-title">' + esc(item.title) + '</div>'
        + '<div class="com-card-desc">' + esc(desc) + '</div>'
        + '<div class="com-card-tags">' + esc(item.author || '') + (item.tags ? ' · ' + esc(item.tags) : '') + '</div>'
        + '<div class="com-card-actions"><button class="sh-btn primary" data-import="' + item.id + '">导入到本地</button>'
        + '<button class="sh-btn" data-like="' + item.id + '">点赞</button>'
        + (mine ? '<button class="sh-btn" data-del="' + item.id + '" style="color:#b91c1c">删除</button>' : '')
        + '</div>'
        + '</div>';
    }).join('') + '</div>';
    bindCardActions();
  }

  function bindCardActions() {
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-import]'), function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute('data-import');
        btn.textContent = '导入中…';
        api('/community/' + id + '/download').then(function (res) {
          if (!res.ok) { alert(res.d.detail || '下载失败'); btn.textContent = '导入到本地'; return; }
          return importToLocal(res.d).then(function () {
            alert('已导入到本地试剂配置库/实验方案库');
            btn.textContent = '导入到本地';
          }).catch(function (e) {
            alert('导入失败：' + e.message);
            btn.textContent = '导入到本地';
          });
        });
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-like]'), function (btn) {
      btn.onclick = function () {
        api('/community/' + btn.getAttribute('data-like') + '/like', { method: 'POST', body: '{}' }).then(function () { load(); });
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-del]'), function (btn) {
      btn.onclick = function () {
        if (!confirm('确定删除这条社区内容？')) return;
        api('/community/' + btn.getAttribute('data-del'), { method: 'DELETE' }).then(function (res) {
          if (!res.ok) { alert(res.d.detail || '删除失败'); return; }
          load();
        });
      };
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
      host.innerHTML = '<div class="com-publish">'
        + '<button class="sh-btn" id="com-publish-back">← 返回社区</button>'
        + '<div class="com-detail-title">发布到远程社区</div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">选择本地内容</label><select id="com-pick" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px">' + options + '</select></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">标题</label><input id="com-title" placeholder="不填则用原名" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">作者</label><input id="com-author" placeholder="留空用登录名" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:10px"><label style="font-size:12px;color:#475569">标签</label><input id="com-tags" placeholder="植物,1/2MS,母液" style="width:100%;margin-top:4px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:9px"></div>'
        + '<div style="margin-top:12px"><button class="sh-btn primary" id="com-publish-save">发布</button><span id="com-publish-msg" style="font-size:12px;color:#64748b;margin-left:8px"></span></div>'
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
      + '<span style="font-weight:700;font-size:14px;color:#0f172a">🌐 远程社区</span>'
      + '<input id="com-search" type="search" placeholder="搜索标题 / 作者 / 标签…">'
      + '<select id="com-kind"><option value="">全部类型</option><option value="reagent_prep">试剂配方</option><option value="protocol">实验方案</option></select>'
      + '<button class="sh-btn" id="com-publish">发布到社区</button>'
      + '<span id="com-user-box" style="margin-left:auto;display:flex;align-items:center;gap:6px"></span>'
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
    fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.settings && d.settings.community_base_url) {
        REMOTE_BASE = String(d.settings.community_base_url).replace(/\/+$/, '');
        localStorage.setItem('community_remote_base', REMOTE_BASE);
      }
      userLabel();
      load();
    }).catch(function () {
      userLabel();
      load();
    });
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
