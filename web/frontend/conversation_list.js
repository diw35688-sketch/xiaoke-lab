// DeepSeekHarness 式会话列表：后端会话是唯一事实，聊天框只切换当前会话。
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

  function cleanEmptyConversations() {
    return fetch('/chat/conversations').then(function (r) { return r.json(); }).then(function (d) {
      var active = currentId();
      var empties = (d.items || []).filter(function (item) {
        return !item.message_count && item.id !== active;
      });
      return Promise.all(empties.map(function (item) {
        return fetch('/chat/conversations/' + encodeURIComponent(item.id), { method: 'DELETE' });
      })).then(function () { return load(); });
    });
  }
  window.cleanEmptyConversations = cleanEmptyConversations;

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
    return fetch('/chat/conversations').then(function (r) { return r.json(); }).then(function (d) {
      var active = currentId();
      host.innerHTML = (d.items || []).map(function (item) {
        var last = String(item.last_message || '').replace(/\s+/g, ' ').slice(0, 30);
        return '<div class="sh-conversation' + (item.id === active ? ' active' : '') + '" data-id="' + esc(item.id) + '" data-title="' + esc(item.title || '新会话') + '">'
          + '<div class="sh-conversation-title">' + esc(item.title || '新会话') + '</div>'
          + '<div class="sh-conversation-meta">' + esc(last || '空会话') + '</div>'
          + '<button class="sh-conversation-delete" title="删除">×</button></div>';
      }).join('') || '<div style="font-size:11px;color:#94a3b8;padding:6px 9px">暂无会话</div>';
      Array.prototype.forEach.call(host.querySelectorAll('.sh-conversation'), function (row) {
        row.onclick = function (event) {
          if (event.target.closest('.sh-conversation-delete')) return;
          switchTo(row.dataset.id);
        };
        row.ondblclick = function () { renameConversation(row.dataset.id, row.dataset.title); };
        row.querySelector('.sh-conversation-delete').onclick = function (event) {
          event.stopPropagation(); deleteConversation(row.dataset.id);
        };
      });
    });
  }

  document.addEventListener('shell-ready', function () {
    var button = document.getElementById('sh-new-session');
    if (button) button.onclick = createConversation;
    load();
  });
  document.addEventListener('conversation-changed', load);
})();
