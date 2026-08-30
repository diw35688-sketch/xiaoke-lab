// 移动端电脑版外壳：抽屉导航 + 聊天/工作台切换。
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }

  function addTopButtons() {
    var top = el('sh-top');
    if (!top || el('sh-mobile-menu')) return;
    var menu = document.createElement('button');
    menu.id = 'sh-mobile-menu';
    menu.title = '打开导航';
    menu.textContent = '☰';
    menu.onclick = function () {
      document.body.classList.add('mobile-nav-open');
      var overlay = el('sh-mobile-overlay');
      if (overlay) overlay.style.display = 'block';
    };
    var toggle = document.createElement('button');
    toggle.id = 'sh-mobile-view-toggle';
    toggle.title = '切换聊天/工作台';
    toggle.textContent = '💬';
    toggle.onclick = function () {
      window.shellCurrentView && window.shellCurrentView() === 'chat'
        ? document.body.classList.add('mobile-mode-work')
        : document.body.classList.add('mobile-mode-chat');
      if (window.shellShow) window.shellShow('chat');
    };
    var overlay = document.createElement('div');
    overlay.id = 'sh-mobile-overlay';
    overlay.onclick = function () {
      document.body.classList.remove('mobile-nav-open');
      overlay.style.display = 'none';
    };
    top.appendChild(menu);
    top.appendChild(toggle);
    document.body.appendChild(overlay);

    // 点导航项目后关闭抽屉
    document.addEventListener('click', function (e) {
      var item = e.target.closest && e.target.closest('.sh-item');
      if (item) {
        document.body.classList.remove('mobile-nav-open');
        var overlay2 = el('sh-mobile-overlay');
        if (overlay2) overlay2.style.display = 'none';
      }
    });
  }

  function syncMode() {
    var isChat = !window.shellCurrentView || window.shellCurrentView() === 'chat';
    document.body.classList.toggle('mobile-mode-chat', isChat);
    document.body.classList.toggle('mobile-mode-work', !isChat);
  }

  function init() {
    addTopButtons();
    syncMode();
    // 手机端默认收起会话管理，点“会话”按钮后由 shell 的
    // conversation-hidden 类切换滑出/收起。
    var shell = document.getElementById('shell');
    if (shell && window.innerWidth <= 900) {
      shell.classList.add('conversation-hidden');
    }
    window.addEventListener('resize', syncMode);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
