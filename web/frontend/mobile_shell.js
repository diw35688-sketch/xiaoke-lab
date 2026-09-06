// 移动端电脑版外壳：抽屉导航 + 聊天/工作台切换。
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }

  function addTopButtons() {
    var top = el('sh-top');
    if ((!top && !el('sh-chat-head')) || el('sh-mobile-menu')) return;
    var controls = document.createElement('span');
    controls.id = 'sh-mobile-controls';
    var menu = document.createElement('button');
    menu.id = 'sh-mobile-menu';
    menu.title = '打开功能导航';
    menu.setAttribute('aria-label', '打开功能导航');
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
    controls.appendChild(menu);
    controls.appendChild(toggle);
    document.body.appendChild(controls);

    var version = document.createElement('span');
    version.id = 'sh-mobile-version';
    version.textContent = 'v20260903';
    version.style.cssText = 'font-size:10px;color:#94a3b8;background:rgba(37,99,235,.08);border-radius:8px;padding:2px 6px;white-space:nowrap;';
    if (top) top.appendChild(version);

    var side = el('sh-side');
    var brand = side && el('sh-brand');
    if (brand && !el('sh-mobile-drawer-close')) {
      var close = document.createElement('button');
      close.id = 'sh-mobile-drawer-close';
      close.type = 'button';
      close.title = '关闭功能导航';
      close.setAttribute('aria-label', '关闭功能导航');
      close.textContent = '×';
      close.onclick = function () {
        document.body.classList.remove('mobile-nav-open');
        var overlay = el('sh-mobile-overlay');
        if (overlay) overlay.style.display = 'none';
      };
      brand.appendChild(close);
    }

    var overlay = document.createElement('div');
    overlay.id = 'sh-mobile-overlay';
    overlay.onclick = function () {
      document.body.classList.remove('mobile-nav-open');
      overlay.style.display = 'none';
    };
    // 必须放进 #shell 内部：若放到 body 末尾，遮罩会成为 #shell 的兄弟层，
    // 某些浏览器下会把抽屉（#shell 内的 fixed 子元素）整个盖住，导致点了没反应。
    var shellBox = el('shell') || document.body;
    shellBox.appendChild(overlay);

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
