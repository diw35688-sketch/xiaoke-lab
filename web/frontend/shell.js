// 应用外壳：三列布局，参考 deepseek-harness 的 AppFrame。
//   左  侧栏导航
//   中  工作画布：工具调用卡片、思维链、步骤卡片
//   右  对话框
// 中间列是主角，其余列给它让路，而不是浮在它上面。
(function () {
  var AUTO_COLLAPSE = 1240;

  var CSS = [
    'body.shell{margin:0;overflow:hidden}',
    '#shell{position:fixed;inset:0;display:flex;background:var(--n-60);font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;font-size:var(--fs-md);color:var(--n-900)}',
    // 左侧栏：浅色，不再是深蓝黑
    '#sh-side{flex:0 0 216px;background:var(--n-50);border-right:1px solid var(--bd-2);display:flex;flex-direction:column;transition:flex-basis .18s}',
    '#shell.side-collapsed #sh-side{flex-basis:50px}',
    '#sh-brand{padding:14px 16px;font-size:var(--fs-md);font-weight:600;color:var(--n-900);display:flex;align-items:center;gap:8px;white-space:nowrap;overflow:hidden}',
    '#sh-brand span.dot{width:7px;height:7px;border-radius:50%;background:var(--green-500);flex:0 0 7px}',
    '.sh-nav{padding:4px 8px;flex:1;overflow:auto}',
    '.sh-item{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:var(--r-md);cursor:pointer;font-size:var(--fs-md);color:var(--n-700);white-space:nowrap;overflow:hidden;margin-bottom:1px}',
    '.sh-item:hover{background:var(--n-100)}',
    '.sh-item.active{background:var(--brand-50);color:var(--brand-strong);font-weight:500}',
    '.sh-ico{flex:0 0 16px;text-align:center;font-size:12px;opacity:.75}',
    '.sh-sec{font-size:var(--fs-xs);color:var(--n-500);padding:12px 10px 4px;white-space:nowrap;overflow:hidden}',
    '#shell.side-collapsed .sh-label,#shell.side-collapsed .sh-sec,#shell.side-collapsed #sh-brand b{display:none}',
    '#sh-foot{padding:8px;border-top:1px solid var(--bd-1)}',
    // 中间画布
    '#sh-center{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--n-60)}',
    '#sh-top{height:44px;flex:0 0 44px;background:var(--n-00);border-bottom:1px solid var(--bd-2);display:flex;align-items:center;padding:0 14px;gap:10px}',
    '#sh-title{font-size:var(--fs-md);font-weight:600;color:var(--n-900)}',
    '#sh-status{font-size:var(--fs-sm);color:var(--n-600);margin-left:auto;display:flex;align-items:center;gap:6px}',
    '.sh-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--r-sm);background:var(--n-75);font-size:var(--fs-xs);color:var(--n-700)}',
    '.sh-pill.warn{background:var(--red-50);color:var(--red-600)}',
    '.sh-pill.ok{background:var(--green-100);color:var(--green-900)}',
    '#sh-canvas{flex:1;overflow:auto;padding:16px 20px}',
    '#sh-canvas.empty{display:flex;align-items:center;justify-content:center;color:var(--n-500);font-size:var(--fs-md);text-align:center;line-height:1.9}',
    // 右侧对话
    '#sh-chat{flex:0 0 640px;background:var(--n-00);border-left:1px solid var(--bd-1);display:flex;flex-direction:row;transition:flex-basis .18s;min-width:0}',
    '#shell.chat-closed #sh-chat{flex-basis:0;overflow:hidden;border-left:0}',
    '#sh-conversation-panel{flex:0 0 210px;border-right:1px solid var(--bd-1);display:flex;flex-direction:column;min-height:0}',
    '#sh-conversation-panel .sh-panel-title{padding:12px 12px 6px;font-size:12px;font-weight:600;color:var(--n-500)}',
    '#sh-conversation-list{flex:1;overflow:auto;padding:0 8px 8px}',
    '#sh-chat-main{flex:1;min-width:0;display:flex;flex-direction:column}',
    '#sh-chat-head{height:44px;flex:0 0 44px;border-bottom:1px solid var(--bd-1);display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 12px 0 16px;font-size:14px;font-weight:600;color:var(--n-800)}#sh-chat-actions{display:flex;align-items:center;gap:8px}#sh-chat-head .sh-btn{padding:4px 10px;font-size:12px;font-weight:400}#sh-call.active{background:var(--red-500);border-color:var(--red-500);color:#fff}',
    '#sh-chat-host{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}',
    '.sh-btn{border:1px solid var(--bd-2);background:var(--n-00);border-radius:var(--r-md);padding:5px 11px;cursor:pointer;font-size:var(--fs-sm);font-family:inherit;color:var(--n-800)}',
    '.sh-btn:hover{background:var(--n-60)}',
    '.sh-btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}',
    '.sh-btn.primary:hover{background:var(--brand-strong)}',
    // 收拾队友页面里的浮动元素
    '#chat-card .avatar-stage,#chat-card .avatar,#avatar-stage,.assistant-portrait{display:none!important}',
    '#chat-card{background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important}',
    '#chat{padding:16px 16px 10px!important;height:auto!important;display:flex!important;flex-direction:column!important;gap:14px!important}',
    '.chat-form{display:none!important}',
    '.chat-form input#message{flex:1!important;min-width:0!important;padding:8px 11px!important;border:1px solid var(--bd-2)!important;border-radius:var(--r-md)!important;font-size:var(--fs-md)!important;font-family:inherit!important}',
    '.chat-form button{flex:0 0 auto!important;white-space:nowrap!important;padding:8px 14px!important;border-radius:var(--r-md)!important;font-size:var(--fs-sm)!important;font-family:inherit!important;border:1px solid var(--bd-2)!important;background:var(--n-00)!important;cursor:pointer!important;writing-mode:horizontal-tb!important;width:auto!important;height:auto!important}',
    '.chat-form button.send{background:var(--brand)!important;border-color:var(--brand)!important;color:#fff!important}',
    '.voice-row{display:none!important}',
    '#sh-new-session{width:calc(100% - 18px);margin:2px 9px 6px;text-align:left;color:var(--brand-strong)}',
    '.sh-conversation{position:relative;padding:7px 28px 7px 9px;border-radius:var(--r-md);cursor:pointer;color:var(--n-700);overflow:hidden;margin-bottom:2px}',
    '.sh-conversation:hover{background:var(--n-100)}',
    '.sh-conversation.active{background:var(--brand-50);color:var(--brand-strong)}',
    '.sh-conversation-title{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sh-conversation-meta{font-size:10px;color:var(--n-500);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}',
    '.sh-conversation-delete{position:absolute;right:5px;top:8px;border:0;background:transparent;color:var(--n-400);cursor:pointer;display:none}',
    '.sh-conversation:hover .sh-conversation-delete{display:block}',
      '@media(max-width:820px){#sh-side{display:none!important}#shell{flex-direction:column!important}#sh-center{flex:0 0 42vh!important}#sh-chat{flex:1 1 58vh!important;border-left:0!important;border-top:1px solid var(--bd-1)!important}#sh-toggle-chat{display:none!important}}'

  ].join('');

  var HTML = [
    '<div id="sh-side">',
    '  <div id="sh-brand"><span class="dot"></span><b>实验语音助手</b></div>',
    '  <div class="sh-nav">',
    '    <div class="sh-sec">工作台</div>',
    '    <div class="sh-item active" data-view="run"><span class="sh-ico">◈</span><span class="sh-label">实验进行中</span></div>',
    '    <div class="sh-item" data-view="calculator"><span class="sh-ico">∑</span><span class="sh-label">分子量计算</span></div>',
    '    <div class="sh-item" data-view="protocols"><span class="sh-ico">☰</span><span class="sh-label">实验方案</span></div>',
    '    <div class="sh-item" data-view="reagent_prep"><span class="sh-ico">🧪</span><span class="sh-label">试剂配置库</span></div>',
    '    <div class="sh-item" data-view="reagents"><span class="sh-ico">⚗</span><span class="sh-label">试剂安全库</span></div>',
    '    <div class="sh-item" data-view="records"><span class="sh-ico">▤</span><span class="sh-label">本次记录</span></div>',
    '    <div class="sh-sec">配置</div>',
    '    <div class="sh-item" data-view="settings"><span class="sh-ico">⚙</span><span class="sh-label">设置</span></div>',
    '  </div>',
    '  <div id="sh-foot"><button class="sh-btn" id="sh-collapse" style="width:100%">收起侧栏</button></div>',
    '</div>',
    '<div id="sh-center">',
    '  <div id="sh-top"><span id="sh-title">实验进行中</span>',
    '    <div id="sh-status"></div>',
    '    <button class="sh-btn" id="sh-toggle-chat">隐藏对话</button></div>',
    '  <div id="sh-canvas"></div>',
    '</div>',
    '<div id="sh-chat">',
    '  <div id="sh-conversation-panel">',
    '    <div class="sh-panel-title">会话管理</div>',
    '    <button class="sh-btn" id="sh-new-session" type="button">＋ 新会话</button>',
    '    <div id="sh-conversation-list"></div>',
    '  </div>',
    '  <div id="sh-chat-main">',
    '    <div id="sh-chat-head"><span>实验对话</span><span id="sh-chat-actions"><button class="sh-btn" id="sh-phone" type="button">手机</button><button class="sh-btn" id="sh-call" type="button">通话</button><button class="sh-btn" id="sh-new-chat" type="button">新对话</button></span></div>',
    '    <div id="sh-chat-host"></div>',
    '  </div>',
    '</div>'
  ].join('');

  function el(id) { return document.getElementById(id); }

  var VIEWS = {};
  window.shellRegisterView = function (name, render) { VIEWS[name] = render; };
  window.shellCanvas = function () { return el('sh-canvas'); };

  var current = 'run';
  function show(view) {
    current = view;
    Array.prototype.forEach.call(document.querySelectorAll('.sh-item'), function (n) {
      n.classList.toggle('active', n.dataset.view === view);
    });
    var titles = { run: '实验进行中', calculator: '分子量计算', protocols: '实验方案', reagent_prep: '试剂配置库', reagents: '试剂安全库',
                   records: '本次记录', settings: '设置' };
    el('sh-title').textContent = titles[view] || view;
    var canvas = el('sh-canvas');
    canvas.classList.remove('empty');
    if (view === 'run') {
      if (window.runCanvasRender) window.runCanvasRender(canvas);
      return;
    }
    canvas.innerHTML = '<div style="color:#94a3b8;font-size:13px">加载中…</div>';
    if (VIEWS[view]) VIEWS[view](canvas);
    else canvas.innerHTML = '<div style="color:#94a3b8;font-size:13px">此页尚未接入</div>';
  }
  window.shellShow = show;
  window.shellCurrentView = function () { return current; };
  window.shellStatus = function (html) { el('sh-status').innerHTML = html; };
  window.appApplyUiAction = function (action) {
    if (!action || typeof action !== 'object') return;
    if (action.type === 'navigate' && action.view) {
      show(action.view);
      return;
    }
    if (action.type === 'refresh') {
      show(current);
      return;
    }
    if (action.type === 'focus_chat') {
      var input = document.getElementById('message');
      if (input) input.focus();
    }
  };

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var chatCard = document.querySelector('#chat-card');
    var main = document.querySelector('main');
    var shell = document.createElement('div');
    shell.id = 'shell';
    shell.innerHTML = HTML;
    document.body.appendChild(shell);
    document.body.classList.add('shell');

    // 接管队友已有的聊天卡片整块，不重写其聊天逻辑
    if (chatCard) {
      chatCard.style.border = '0';
      chatCard.style.borderRadius = '0';
      chatCard.style.boxShadow = 'none';
      chatCard.style.flex = '1';
      chatCard.style.minHeight = '0';
      chatCard.style.display = 'flex';
      chatCard.style.flexDirection = 'column';
      var head = chatCard.querySelector('.chat-head');
      if (head) head.style.display = 'none';
      el('sh-chat-host').appendChild(chatCard);
    }
    if (main) main.style.display = 'none';

    Array.prototype.forEach.call(document.querySelectorAll('.sh-item'), function (n) {
      n.onclick = function () { show(n.dataset.view); };
    });
    el('sh-collapse').onclick = function () {
      var on = shell.classList.toggle('side-collapsed');
      el('sh-collapse').textContent = on ? '展开' : '收起侧栏';
    };
    el('sh-toggle-chat').onclick = function () {
      var closed = shell.classList.toggle('chat-closed');
      el('sh-toggle-chat').textContent = closed ? '显示对话' : '隐藏对话';
    };

    function responsive() {
      if (window.innerWidth < AUTO_COLLAPSE) shell.classList.add('side-collapsed');
    }
    responsive();
    window.addEventListener('resize', responsive);

    document.dispatchEvent(new CustomEvent('shell-ready'));
    show('run');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
