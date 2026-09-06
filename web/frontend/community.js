/* 社区：使用全局登录（lab_session Cookie），不再维护独立社区账号。 */
(function () {
  var host, listEl;
  var currentUser = null;
  var state = { q: '', kind: '', tag: '', sort: 'latest' };
  var allItems = [];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function api(path, method, body) {
    var opts = { method: method || 'GET' };
    if (body) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = typeof body === 'string' ? body : JSON.stringify(body);
    }
    return fetch('/community-proxy' + path, opts).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).catch(function () { return { ok: false, d: { detail: '社区服务请求失败' } }; });
  }

  function kindBadge(kind) {
    if (kind === 'reagent_prep') return '<span class="ch-badge ch-badge-prep">🧪 试剂配方</span>';
    if (kind === 'protocol') return '<span class="ch-badge ch-badge-protocol">☰ 实验方案</span>';
    return '<span class="ch-badge">' + esc(kind) + '</span>';
  }

  function initials(name) {
    return (name || '?').slice(0, 1).toUpperCase();
  }

  function refreshAuth() {
    return fetch('/auth/state').then(function (r) { return r.json(); }).then(function (s) {
      currentUser = s.authenticated ? s.user : null;
      userLabel();
      return currentUser;
    }).catch(function () { currentUser = null; userLabel(); return null; });
  }

  function userLabel() {
    var box = host.querySelector('#com-user-box');
    if (!box) return;
    if (!currentUser) {
      box.innerHTML = '<button class="ch-btn primary" id="com-login-btn">登录</button>';
      box.querySelector('#com-login-btn').onclick = function () { location.href = '/login'; };
      return;
    }
    box.innerHTML = '<span class="ch-user">' + esc(currentUser.username || '') + (currentUser.is_admin ? ' <span class="ch-crown">👑</span>' : '') + '</span> '
      + '<button class="ch-btn ghost" id="com-logout">退出</button>';
    box.querySelector('#com-logout').onclick = function () {
      fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' }).then(function () {
        currentUser = null;
        userLabel();
        load();
      });
    };
  }

  function load() {
    state.q = (host.querySelector('#com-search') || { value: '' }).value.trim().toLowerCase();
    if (listEl) listEl.innerHTML = '<div class="com-empty">正在加载模板…</div>';
    api('/community?limit=500').then(function (res) {
      if (!res.ok) { listEl.innerHTML = '<div class="com-empty">' + esc(res.d.detail || '加载失败') + '</div>'; return; }
      allItems = res.d.items || [];
      renderTags();
      applyFilter();
    });
  }

  function topTags() {
    var counts = {};
    allItems.forEach(function (item) {
      String(item.tags || '').split(',').forEach(function (raw) {
        var t = raw.trim();
        if (t) counts[t] = (counts[t] || 0) + 1;
      });
    });
    return Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, 12);
  }

  function renderTags() {
    var box = host.querySelector('#com-tags');
    if (!box) return;
    var tags = topTags();
    box.innerHTML = '<button class="com-cat' + (state.tag ? '' : ' active') + '" data-tag="">全部标签</button>' +
      tags.map(function (t) {
        return '<button class="com-cat' + (state.tag === t ? ' active' : '') + '" data-tag="' + esc(t) + '">' + esc(t) + '</button>';
      }).join('');
    Array.prototype.forEach.call(box.querySelectorAll('[data-tag]'), function (btn) {
      btn.onclick = function () {
        state.tag = btn.getAttribute('data-tag');
        renderTags();
        applyFilter();
      };
    });
  }

  function filteredItems() {
    var items = allItems.filter(function (item) {
      if (state.kind && item.kind !== state.kind) return false;
      if (state.tag && !String(item.tags || '').split(',').map(function (s) { return s.trim(); }).includes(state.tag)) return false;
      if (state.q) {
        var hay = (item.title + ' ' + (item.author || '') + ' ' + (item.tags || '')).toLowerCase();
        if (hay.indexOf(state.q) < 0) return false;
      }
      return true;
    });
    items = items.slice();
    if (state.sort === 'downloads') items.sort(function (a, b) { return (b.downloads || 0) - (a.downloads || 0); });
    else if (state.sort === 'likes') items.sort(function (a, b) { return (b.likes || 0) - (a.likes || 0); });
    else if (state.sort === 'comments') items.sort(function (a, b) { return (b.comment_count || 0) - (a.comment_count || 0); });
    return items;
  }

  function applyFilter() {
    render(filteredItems());
  }

  function compact(s) {
    return String(s || '').replace(/\s+/g, '');
  }

  function stepText(step) {
    if (!step) return '';
    if (typeof step === 'string') return step;
    if (typeof step === 'object') {
      var title = step.title || '';
      var text = step.instruction || step.text || '';
      // 很多 PDF 抽取结果里 title 是 instruction 的截断前缀，两个都拼会重复。
      // 这种情况只显示 instruction。
      var redundant = false;
      if (title && text) {
        var ct = compact(title);
        var ci = compact(text);
        redundant = ci.indexOf(ct) === 0 || ct.length >= 40;
      }
      if (redundant) return text || title;
      return title && text ? title + '：' + text : (title || text);
    }
    return String(step);
  }

  function stepHtml(content) {
    if (!content || !Array.isArray(content.steps)) return '';
    return '<ol class="ch-steps">' + content.steps.slice(0, 8).map(function (s) {
      return '<li>' + esc(stepText(s)) + '</li>';
    }).join('') + '</ol>';
  }

  function loadComments(mask, entryId) {
    api('/community/' + entryId + '/comments').then(function (res) {
      var box = mask.querySelector('#ch-comments');
      if (!box) return;
      var items = (res.ok && res.d.items) || [];
      box.innerHTML = items.map(function (c) {
        return '<div style="padding:8px 0;border-bottom:1px dashed #eef2f7">'
          + '<div style="font-size:12px;color:#64748b">' + esc(c.user_name || c.user_id || '') + ' · ' + esc(c.created_at || '') + '</div>'
          + '<div style="font-size:13px;color:#334155">' + esc(c.content) + '</div></div>';
      }).join('') || '<div style="color:#94a3b8;font-size:12px">还没有评论。</div>';
    });
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
      + '<div class="ch-meta-small">' + esc(item.author || '') + ' · ' + (item.downloads || 0) + ' 次导入 · ' + (item.likes || 0) + ' 点赞 · ' + (item.comment_count || 0) + ' 评论</div></div>'
      + '<button class="ch-btn ghost" id="ch-detail-close">✕</button></div>'
      + (c.purpose ? '<div class="ch-desc">' + esc(c.purpose) + '</div>' : '')
      + (meta.length ? '<div class="ch-meta">' + meta.join(' · ') + '</div>' : '')
      + (stepHtml(c) ? '<div class="ch-section">模板步骤</div>' + stepHtml(c) : '')
      + '<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap"><button class="ch-btn primary" id="ch-detail-import">导入到本地</button>'
      + '<button class="ch-btn" id="ch-detail-like">点赞 ' + (item.likes || 0) + '</button>'
      + '<button class="ch-btn" id="ch-detail-comment">评论 ' + (item.comment_count || 0) + '</button>'
      + '<button class="ch-btn" id="ch-detail-feedback">反馈修改</button></div>'
      + '<div id="ch-comment-form" style="display:none;margin-top:10px"><textarea id="ch-comment-text" class="ch-input" rows="2" placeholder="写下你的评论…"></textarea>'
      + '<button class="ch-btn primary" id="ch-comment-save" style="margin-top:6px">发表评论</button></div>'
      + '<div id="ch-comments" class="ch-section">评论加载中…</div>'
      + '</div>';
    var mask = document.createElement('div');
    mask.className = 'ch-modal-mask';
    mask.innerHTML = body;
    document.body.appendChild(mask);
    mask.onclick = function (e) { if (e.target === mask) mask.remove(); };
    mask.querySelector('#ch-detail-close').onclick = function () { mask.remove(); };
    mask.querySelector('#ch-detail-import').onclick = function () {
      if (!currentUser) { location.href = '/login'; return; }
      importItem(item, mask.querySelector('#ch-detail-import'));
    };
    mask.querySelector('#ch-detail-like').onclick = function () {
      if (!currentUser) { location.href = '/login'; return; }
      api('/community/' + item.id + '/like', 'POST', {}).then(function (res) {
        load();
        var btn = mask.querySelector('#ch-detail-like');
        if (btn && res && res.ok) btn.textContent = '点赞 ' + (res.d.likes || 0);
      });
    };
    mask.querySelector('#ch-detail-comment').onclick = function () {
      if (!currentUser) { location.href = '/login'; return; }
      mask.querySelector('#ch-comment-form').style.display = mask.querySelector('#ch-comment-form').style.display === 'none' ? '' : 'none';
    };
    mask.querySelector('#ch-detail-feedback').onclick = function () {
      if (!currentUser) { location.href = '/login'; return; }
      var form = mask.querySelector('#ch-comment-form');
      var textarea = mask.querySelector('#ch-comment-text');
      form.style.display = '';
      if (textarea) textarea.placeholder = '请反馈需要修改的内容（如某一步骤有误、参数不对，我们会通知作者）…';
      textarea.focus();
    };
    mask.querySelector('#ch-comment-save').onclick = function () {
      var text = mask.querySelector('#ch-comment-text').value.trim();
      if (!text) return;
      api('/community/' + item.id + '/comments', 'POST', { content: text }).then(function (res) {
        if (!res.ok) { alert(res.d.detail || '评论失败'); return; }
        mask.querySelector('#ch-comment-text').value = '';
        mask.querySelector('#ch-comment-form').style.display = 'none';
        load();
        loadComments(mask, item.id);
      });
    };
    loadComments(mask, item.id);
  }

  function render(items) {
    if (!items.length) {
      listEl.innerHTML = '<div class="com-empty">还没有公开模板。登录后发布一个试试。</div>';
      return;
    }
    listEl.innerHTML = '<div class="ch-grid">' + items.map(function (item) {
      var c = item.content || {};
      var desc = c.purpose || (c.summary || ((c.steps || []).length + ' 个步骤') || '');
      return '<div class="ch-card" data-id="' + item.id + '">'
        + '<div class="ch-card-top">' + kindBadge(item.kind)
        + '<span class="ch-avatar" title="' + esc(item.author || '') + '">' + initials(item.author || '?') + '</span></div>'
        + '<div class="ch-card-title">' + esc(item.title) + '</div>'
        + '<div class="ch-card-desc">' + esc(desc) + '</div>'
        + '<div class="ch-card-tags">' + (item.tags ? esc(item.tags).split(',').slice(0,3).map(function(t){return '<span class="ch-tag">'+esc(t.trim())+'</span>';}).join('') : esc(item.author || '')) + '</div>'
        + '<div class="ch-card-foot"><span class="ch-stat">⬇ ' + (item.downloads || 0) + '</span><span class="ch-stat">♥ ' + (item.likes || 0) + '</span><span class="ch-stat">💬 ' + (item.comment_count || 0) + '</span>'
        + '<button class="ch-btn small primary" data-import="' + item.id + '">导入</button>'
        + '</div></div>';
    }).join('') + '</div>';

    Array.prototype.forEach.call(listEl.querySelectorAll('.ch-card'), function (card) {
      card.onclick = function (e) {
        if (e.target.closest('[data-import]')) return;
        var item = items.filter(function (x) { return x.id == card.getAttribute('data-id'); })[0];
        if (item) detailModal(item);
      };
    });
    Array.prototype.forEach.call(listEl.querySelectorAll('[data-import]'), function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        if (!currentUser) { location.href = '/login'; return; }
        var item = items.filter(function (x) { return x.id == btn.getAttribute('data-import'); })[0];
        importItem(item, btn);
      };
    });
  }

  function importToLocal(entry) {
    var content = entry.content || entry;
    if (entry.kind === 'reagent_prep') {
      return fetch('/reagent-prep/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reagent_prep: content }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) { if (!res.ok) throw new Error(res.d.detail || '试剂配置导入失败'); return true; });
    }
    if (entry.kind === 'protocol') {
      return fetch('/protocols/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ protocol: content }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) { if (!res.ok) throw new Error(res.d.detail || '方案导入失败'); return true; });
    }
    return Promise.reject(new Error('未知类型'));
  }

  function importItem(item, btn) {
    var old = btn.textContent;
    btn.textContent = '导入中…';
    api('/community/' + item.id + '/download', 'GET').then(function (res) {
      if (!res.ok) { alert(res.d.detail || '下载失败'); btn.textContent = old; return; }
      return importToLocal(res.d).then(function () {
        btn.textContent = '已导入';
        // 导入后直接进入对应功能页，不再停留在社区列表。
        if (window.shellShow) {
          var kind = res.d.kind || item.kind;
          window.shellShow(kind === 'protocol' ? 'protocols' : 'reagent_prep');
        }
        load();
      }).catch(function (e) {
        alert('导入失败：' + e.message);
        btn.textContent = old;
      });
    });
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
        + '<div style="margin-top:10px"><label class="ch-label">标签</label><input id="com-tags" class="ch-input" placeholder="植物,1/2MS,母液"></div>'
        + '<div style="margin-top:12px"><button class="ch-btn primary" id="com-publish-save">发布</button><span id="com-publish-msg" style="font-size:12px;color:#64748b;margin-left:8px"></span></div>'
        + '</div>';
      host.querySelector('#com-publish-back').onclick = init;
      host.querySelector('#com-publish-save').onclick = function () {
        if (!currentUser) { location.href = '/login'; return; }
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
        api('/community', 'POST', {
          kind: kind,
          title: title,
          content: selected,
          tags: host.querySelector('#com-tags').value.trim()
        }).then(function (res) {
          if (!res.ok) { host.querySelector('#com-publish-msg').textContent = res.d.detail || '发布失败'; return; }
          alert('发布成功');
          init();
        });
      };
    });
  }

  function importUrlModal() {
    if (!currentUser) { location.href = '/login'; return; }
    var mask = document.createElement('div');
    mask.className = 'ch-modal-mask';
    mask.innerHTML = '<div class="ch-modal" style="max-width:560px">'
      + '<div class="ch-modal-head"><div><div class="ch-detail-title">从链接导入模板</div>'
      + '<div style="color:#64748b;font-size:12px">粘贴一个可直接访问的 JSON 模板地址，系统会抓取并导入到本地。</div></div>'
      + '<button class="ch-btn ghost" id="com-url-close">✕</button></div>'
      + '<textarea id="com-url-input" class="ch-input" style="height:90px;margin-top:12px" placeholder="https://example.com/template.json"></textarea>'
      + '<div style="margin-top:10px;display:flex;gap:8px"><button class="ch-btn primary" id="com-url-go">导入</button>'
      + '<span id="com-url-msg" style="font-size:12px;color:#64748b"></span></div>'
      + '</div>';
    document.body.appendChild(mask);
    mask.querySelector('#com-url-close').onclick = function () { mask.remove(); };
    mask.querySelector('#com-url-go').onclick = function () {
      var url = mask.querySelector('#com-url-input').value.trim();
      var msg = mask.querySelector('#com-url-msg');
      if (!url) { msg.textContent = '请输入链接'; return; }
      msg.textContent = '导入中…';
      fetch('/community/import-url', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
      }).then(function (r) { return r.json().then(function (d) { return {ok: r.ok, d: d}; }); })
        .then(function (res) {
          if (!res.ok) { msg.textContent = res.d.detail || '导入失败'; msg.style.color = '#dc2626'; return; }
          msg.textContent = '已导入本地：' + (res.d.title || ''); msg.style.color = '#047857';
          setTimeout(function () { mask.remove(); load(); }, 800);
        }).catch(function (e) { msg.textContent = '请求失败：' + e.message; msg.style.color = '#dc2626'; });
    };
  }

  function ensureStyles() {
    if (document.getElementById('community-style')) return;
    var style = document.createElement('style');
    style.id = 'community-style';
    style.textContent = [
      '.com-toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:12px;margin-bottom:12px}',
      '.com-toolbar input,.com-toolbar select{padding:9px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:13px;font-family:inherit;background:#fff;color:#0f172a}',
      '.com-toolbar input{flex:1;min-width:160px}',
      '.com-notice{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:10px 14px;font-size:12px;color:#475569;line-height:1.8;margin-bottom:12px}',
      '.com-notice b{color:#0f172a}',
      '.com-cats{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}',
      '.com-cat{padding:6px 12px;border:1px solid #e2e8f0;background:#fff;color:#475569;border-radius:999px;cursor:pointer;font-size:12px;font-family:inherit;transition:all .12s}',
      '.com-cat:hover{background:#f1f5f9}',
      '.com-cat.active{background:#2563eb;border-color:#2563eb;color:#fff}',
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
      '.ch-modal-mask{position:fixed;inset:0;background:rgba(15,23,42,.5);display:flex;align-items:flex-start;justify-content:center;z-index:9999;padding:40px 16px}',
      '.ch-modal{background:#fff;border-radius:18px;padding:24px;max-width:720px;width:100%;max-height:88vh;overflow:auto;box-shadow:0 24px 60px rgba(15,23,42,.28)}',
      '.ch-modal-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}',
      '.ch-detail-title{font-size:20px;font-weight:700;color:#0f172a;margin:10px 0 4px}',
      '.ch-meta-small{color:#94a3b8;font-size:12px}',
      '.ch-desc{color:#334155;font-size:14px;margin:12px 0;line-height:1.7}',
      '.ch-meta{background:#f8fafc;border-radius:10px;padding:10px 12px;font-size:13px;color:#475569;margin-bottom:10px}',
      '.ch-section{font-weight:700;color:#0f172a;margin:14px 0 6px}',
      '.ch-steps{margin:0;padding-left:22px;color:#475569;font-size:13px;line-height:1.9;white-space:pre-wrap;word-break:break-word}',
      '.ch-label{display:block;font-size:12px;color:#475569;margin-bottom:4px}',
      '.ch-input{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;font-family:inherit}',
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
      + '<input id="com-search" type="search" placeholder="搜索模板 / 作者 / 标签…" autocomplete="off">'
      + '<select id="com-sort"><option value="latest">最新</option><option value="downloads">导入最多</option><option value="likes">点赞最多</option><option value="comments">评论最多</option></select>'
      + '<button class="ch-btn" id="com-import-url">从链接导入</button>'
      + '<button class="ch-btn primary" id="com-publish">发布模板</button>'
      + '<span id="com-user-box" style="margin-left:auto;display:flex;align-items:center;gap:8px"></span>'
      + '</div>'
      + '<div class="com-notice"><b>社区模板由用户上传/搜集，仅作参考，不保证效果，请根据实验需求修改后使用；欢迎上传分享自己的模板，也支持从链接导入，或点击模板详情反馈修改建议。</b></div>'
      + '<div class="com-cats" id="com-cats">'
      + '<button class="com-cat active" data-kind="">全部</button>'
      + '<button class="com-cat" data-kind="reagent_prep">🧪 试剂配方</button>'
      + '<button class="com-cat" data-kind="protocol">☰ 实验方案</button>'
      + '</div>'
      + '<div class="com-cats" id="com-tags"></div>'
      + '<div id="com-list"></div>';
    listEl = host.querySelector('#com-list');
    var search = host.querySelector('#com-search');
    var sort = host.querySelector('#com-sort');
    search.addEventListener('input', debounce(function () { state.q = search.value.trim().toLowerCase(); applyFilter(); }, 250));
    sort.addEventListener('change', function () { state.sort = sort.value; applyFilter(); });
    Array.prototype.forEach.call(host.querySelectorAll('#com-cats [data-kind]'), function (btn) {
      btn.onclick = function () {
        state.kind = btn.getAttribute('data-kind');
        Array.prototype.forEach.call(host.querySelectorAll('#com-cats [data-kind]'), function (b) { b.classList.toggle('active', b === btn); });
        applyFilter();
      };
    });
    host.querySelector('#com-publish').onclick = function () {
      if (!currentUser) { location.href = '/login'; return; }
      publishForm();
    };
    host.querySelector('#com-import-url').onclick = function () {
      importUrlModal();
    };
    refreshAuth().then(load);
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
