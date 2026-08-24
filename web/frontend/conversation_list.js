// DeepSeekHarness 式会话列表：后端会话是唯一事实，聊天框只切换当前会话。
// 支持搜索、重命名、删除、相对时间、消息数。
(function () {
  var KEY = 'lab-agent-conversation-id';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function currentId() { return localStorage.getItem(KEY) || ''; }

  function switchTo(id) {
    if (!id) return;
    if (window.switchConversation) window.switchConversation(id);
    else {
      localStorage.setItem(KEY, id);
      location.reload();
    }
  }

  function createConversation() {
    return fetch('/chat/conversations', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
    }).then(function (r) { return r.json(); }).then(function (d) {
      switchTo(d.conversation_id);
      document.dispatchEvent(new CustomEvent('conversation-changed'));
      return d.conversation_id;
    });
  }
  window.appNewConversation = createConversation;

  function parseTime(str) {
    var t = str ? new Date(String(str).replace(' ', 'T')) : null;
    return t && !isNaN(t.getTime()) ? t : null;
  }

  function timeAgo(str) {
    if (!str) return '';
    var t = parseTime(str);
    if (!t) return '';
    var diff = Date.now() - t.getTime();
    var minutes = Math.floor(diff / 60000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return minutes + ' 分钟前';
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + ' 小时前';
    var days = Math.floor(hours / 24);
    if (days === 1) return '昨天';
    if (days < 7) return days + ' 天前';
    return t.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
  }

  function renameConversation(id, currentTitle) {
    var title = prompt('会话名称', currentTitle || '');
    if (!title || title.trim() === currentTitle) return;
    fetch('/chat/conversations/' + encodeURIComponent(id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.trim() })
    }).then(load);
  }

  function deleteConversation(id) {
    if (!confirm('删除这个会话及其聊天历史？实验结构化记录不会被删除。')) return;
    fetch('/chat/conversations/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(function () {
        if (currentId() === id) localStorage.removeItem(KEY);
        return load();
      }).then(function () {
        if (!currentId()) createConversation();
      });
  }

  function load() {
    var host = document.getElementById('sh-conversation-list');
    if (!host) return Promise.resolve();
    var searchEl = document.getElementById('sh-conversation-search');
    var q = searchEl ? searchEl.value.trim().toLowerCase() : '';
    return fetch('/chat/conversations').then(function (r) { return r.json(); }).then(function (d) {
      var active = currentId();
      var items = (d.items || []).filter(function (item) {
        if (!q) return true;
        var hay = String(item.title || '') + ' ' + String(item.last_message || '');
        return hay.toLowerCase().indexOf(q) >= 0;
      });
      host.innerHTML = items.map(function (item) {
        var last = String(item.last_message || '').replace(/\s+/g, ' ').slice(0, 34);
        return '<div class="sh-conversation' + (item.id === active ? ' active' : '') + '" data-id="' + esc(item.id) + '" data-title="' + esc(item.title || '新会话') + '">'
          + '<div class="sh-conversation-title">' + esc(item.title || '新会话') + '</div>'
          + '<div class="sh-conversation-meta">' + esc(last || '空会话') + '</div>'
          + '<div class="sh-conversation-sub">' + esc(timeAgo(item.updated_at)) + (item.message_count ? ' · ' + item.message_count + ' 条' : '') + '</div>'
          + '<div class="sh-conversation-actions">'
          + '<button class="sh-conversation-rename" title="重命名">✎</button>'
          + '<button class="sh-conversation-delete" title="删除">×</button>'
          + '</div></div>';
      }).join('') || '<div style="font-size:11px;color:#94a3b8;padding:6px 9px">' + (q ? '没有匹配的会话' : '暂无会话') + '</div>';
      Array.prototype.forEach.call(host.querySelectorAll('.sh-conversation'), function (row) {
        row.onclick = function (event) {
          if (event.target.closest('.sh-conversation-delete') || event.target.closest('.sh-conversation-rename')) return;
          switchTo(row.dataset.id);
        };
        row.ondblclick = function () { renameConversation(row.dataset.id, row.dataset.title); };
        row.querySelector('.sh-conversation-rename').onclick = function (event) {
          event.stopPropagation(); renameConversation(row.dataset.id, row.dataset.title);
        };
        row.querySelector('.sh-conversation-delete').onclick = function (event) {
          event.stopPropagation(); deleteConversation(row.dataset.id);
        };
      });
    });
  }

  document.addEventListener('shell-ready', function () {
    var button = document.getElementById('sh-new-session');
    if (button) button.onclick = createConversation;
    var search = document.getElementById('sh-conversation-search');
    if (search) search.addEventListener('input', load);
    load();
  });
  document.addEventListener('conversation-changed', load);
})();
