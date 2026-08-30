// 应用外壳：三列布局，参考 deepseek-harness 的 AppFrame。
//   左  侧栏导航
//   中  工作画布：工具调用卡片、思维链、步骤卡片
//   右  对话框
// 中间列是主角，其余列给它让路，而不是浮在它上面。
(function () {
  var AUTO_COLLAPSE = 1240;

  // 「纸上实验台」皮肤：默认 paper，经典外观完整保留、随时切回。
  // 皮肤只在 body 上挂一个类，全部差异都在 theme.css 的 body.skin-paper 块里。
  var SKIN_KEY = 'lab-skin';
  var skin = 'paper';
  try { skin = localStorage.getItem(SKIN_KEY) || 'paper'; } catch (_) {}
  if (skin === 'paper') document.body.classList.add('skin-paper');

  var CSS = [
    'body.shell{margin:0;overflow:hidden}',
    // 老页面（index.html 内联应用）整体埋掉：外壳接管后它只在底层耗资源，
    // 任何样式失效都不允许它"透出来"（2026-08-30 截图事故：主题变量失联时深色老侧栏穿透）。
    'body.shell .app>.sidebar{display:none!important}',
    // 关键背景一律带字面量兜底：theme.css 加载失败/缓存旧版时外壳也不得透明。
    '#shell{position:fixed;inset:0;display:flex;background:var(--n-60,#f5f6f7);font-family:var(--font-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif);font-size:var(--fs-md,14px);color:var(--n-900,#1b1b1c)}',
    // 左侧栏：浅色，不再是深蓝黑
    '#sh-side{flex:0 0 220px;background:var(--n-50,#f9fafb);border-right:1px solid var(--bd-2,rgba(0,0,0,.1));display:flex;flex-direction:column;transition:flex-basis .18s}',
    '#shell.side-collapsed #sh-side{flex-basis:54px}',
    '#sh-brand{padding:16px 14px 12px;font-size:var(--fs-md);font-weight:600;color:var(--n-900);display:flex;align-items:center;gap:10px;white-space:nowrap;overflow:hidden}',
    '#sh-brand .mark{display:grid;place-items:center;width:28px;height:28px;border-radius:9px;background:var(--brand);color:#fff;flex:0 0 28px;box-shadow:var(--sh-1)}',
    '#sh-brand .mark svg{display:block}',
    '.sh-nav{padding:4px 8px;flex:1;overflow:auto}',
    '.sh-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:var(--r-md);cursor:pointer;font-size:var(--fs-md);color:var(--n-700);white-space:nowrap;overflow:hidden;margin-bottom:1px;transition:background .12s}',
    '.sh-item:hover{background:var(--n-100)}',
    '.sh-item.active{background:var(--brand-50);color:var(--brand-strong);font-weight:500}',
    '.sh-ico{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;flex:0 0 18px;opacity:.8}',
    '.sh-ico svg{display:block}',
    '.sh-item.active .sh-ico{opacity:1}',
    '.sh-sec{font-size:var(--fs-xs);color:var(--n-500);padding:14px 10px 5px;letter-spacing:.02em;white-space:nowrap;overflow:hidden}',
    '#shell.side-collapsed .sh-label,#shell.side-collapsed .sh-sec,#shell.side-collapsed #sh-brand b{display:none}',
    '#sh-foot{padding:8px;border-top:1px solid var(--bd-1)}',
    // 管理画布与聊天互斥显示，不再左右并排。
    '#sh-center{flex:1;min-width:320px;display:flex;flex-direction:column;background:var(--n-60,#f5f6f7)}',
    '#sh-top{height:44px;flex:0 0 44px;background:var(--n-00,#fff);border-bottom:1px solid var(--bd-2,rgba(0,0,0,.1));display:flex;align-items:center;padding:0 14px;gap:10px}',
    '#sh-title{font-size:var(--fs-md);font-weight:600;color:var(--n-900)}',
    '#sh-status{font-size:var(--fs-sm);color:var(--n-600);margin-left:auto;display:flex;align-items:center;gap:6px}',
    '#sh-notify{position:relative;margin-left:auto;padding:5px 9px;display:inline-flex;align-items:center;color:var(--n-600)}',
    '#sh-notify svg{display:block}',
    '#sh-notify-badge{position:absolute;top:-4px;right:-4px;min-width:15px;height:15px;border-radius:999px;background:#ef4444;color:#fff;font-size:9px;display:none;align-items:center;justify-content:center;padding:0 3px}',
    '#sh-notify.has-unread #sh-notify-badge{display:flex}',
    '.sh-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--r-sm);background:var(--n-75);font-size:var(--fs-xs);color:var(--n-700)}',
    '.sh-pill.warn{background:var(--red-50);color:var(--red-600)}',
    '.sh-pill.ok{background:var(--green-100);color:var(--green-900)}',
    '#sh-canvas{flex:1;overflow:auto;padding:16px 20px}',
    '#sh-canvas.empty{display:flex;align-items:center;justify-content:center;color:var(--n-500);font-size:var(--fs-md);text-align:center;line-height:1.9}',
    // 空状态：纸面里就是「一张还没写字的纸」
    '.sh-blank{max-width:560px;margin:8vh auto 0;text-align:center;color:var(--n-600,#81858c)}',
    '.sh-blank-title{font-size:19px;font-weight:600;color:var(--n-800,#353638);margin-bottom:10px}',
    '.sh-blank-text{font-size:var(--fs-md,14px);line-height:2;margin:0 0 20px}',
    '.sh-blank-acts{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}',
    'body.skin-paper .sh-blank-title{font-family:var(--f-kai,"KaiTi",serif);font-size:22px;letter-spacing:.06em}',
    // 右侧对话
    '#sh-chat-resizer{flex:0 0 9px;cursor:col-resize;background:rgba(148,163,184,.12);position:relative;z-index:5;border-left:1px solid var(--bd-2);border-right:1px solid var(--bd-2);transition:background .15s}',
    '#sh-chat-resizer:hover,#sh-chat-resizer.dragging{background:rgba(59,103,232,.25)}',
    '#sh-chat{flex:0 0 640px;background:var(--n-00,#fff);border-left:1px solid var(--bd-1,rgba(0,0,0,.04));display:flex;flex-direction:row;transition:flex-basis .18s;min-width:0;position:relative}',
    '#shell.chat-closed #sh-chat{flex-basis:0;overflow:hidden;border-left:0}',
    '#sh-toggle-conversation.active{background:var(--brand-50);color:var(--brand-strong)}',
    '#shell.conversation-hidden #sh-conversation-panel{display:none!important;border-right:0}',
    '#sh-conversation-panel{position:absolute;left:0;top:0;bottom:0;width:236px;background:var(--n-00);border-right:1px solid var(--bd-1);display:flex;flex-direction:column;min-height:0;z-index:20;box-shadow:8px 0 24px rgba(15,23,42,.10)}',
    '#sh-conversation-panel .sh-panel-title{display:flex;align-items:center;justify-content:space-between;padding:12px 12px 6px;font-size:12px;font-weight:600;color:var(--n-500)}',
    '#sh-close-conversation{border:0;background:transparent;color:var(--n-400);cursor:pointer;font-size:16px;line-height:1;padding:0 2px}',
    '#sh-close-conversation:hover{color:#b91c1c}',
    '#sh-conversation-list{flex:1;overflow:auto;padding:0 8px 8px}',
    '#sh-chat-main{flex:1;min-width:0;display:flex;flex-direction:column;width:100%}',
    '#sh-chat-head{height:44px;flex:0 0 44px;border-bottom:1px solid var(--bd-1);display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 12px 0 16px;font-size:14px;font-weight:600;color:var(--n-800)}#sh-chat-actions{display:flex;align-items:center;gap:8px}#sh-chat-head .sh-btn{padding:4px 10px;font-size:12px;font-weight:400}#sh-call.active{background:var(--red-500);border-color:var(--red-500);color:#fff}',
    '#sh-more-wrap{position:relative;display:inline-flex}',
    '#sh-more{position:relative;z-index:3}',
    '#sh-more-menu{position:absolute;right:0;top:calc(100% + 4px);z-index:20;background:var(--n-00);border:1px solid var(--bd-2);border-radius:var(--r-md);box-shadow:0 8px 24px rgba(15,23,42,.12);padding:5px;min-width:84px;display:flex;flex-direction:column;gap:2px}',
    '#sh-more-menu .sh-btn{text-align:left}',
    '#sh-chat-host{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}',
    '.sh-btn{border:1px solid var(--bd-2);background:var(--n-00);border-radius:var(--r-md);padding:5px 11px;cursor:pointer;font-size:var(--fs-sm);font-family:inherit;color:var(--n-800)}',
    '.sh-btn:hover{background:var(--n-60)}',
    '.sh-btn.primary{background:var(--brand);border-color:var(--brand);color:#fff}',
    '.sh-btn.primary:hover{background:var(--brand-strong)}',
    // 收拾队友页面里的浮动元素
    '#chat-card .avatar-stage,#chat-card .avatar,#avatar-stage,.assistant-portrait{display:none!important}',
    '#assistant-avatar.avatar-hidden{display:none!important}',
    '#chat-card{background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important}',
    '#chat{padding:16px 16px 10px!important;height:auto!important;display:flex!important;flex-direction:column!important;gap:14px!important}',
    '.chat-form{display:none!important}',
    '.chat-form input#message{flex:1!important;min-width:0!important;padding:8px 11px!important;border:1px solid var(--bd-2)!important;border-radius:var(--r-md)!important;font-size:var(--fs-md)!important;font-family:inherit!important}',
    '.chat-form button{flex:0 0 auto!important;white-space:nowrap!important;padding:8px 14px!important;border-radius:var(--r-md)!important;font-size:var(--fs-sm)!important;font-family:inherit!important;border:1px solid var(--bd-2)!important;background:var(--n-00)!important;cursor:pointer!important;writing-mode:horizontal-tb!important;width:auto!important;height:auto!important}',
    '.chat-form button.send{background:var(--brand)!important;border-color:var(--brand)!important;color:#fff!important}',
    '.voice-row{display:none!important}',
    '#sh-conversation-search{display:block;width:calc(100% - 18px);margin:6px 9px 4px;box-sizing:border-box;padding:6px 9px;border:1px solid var(--bd-2);border-radius:var(--r-md);font-size:12px;font-family:inherit;background:var(--n-00);color:var(--n-800)}',
    '#sh-conversation-search:focus{outline:2px solid rgba(59,103,232,.2);border-color:var(--brand)}',
    '#sh-new-session{width:calc(100% - 18px);margin:2px 9px 6px;text-align:left;color:var(--brand-strong)}',
    '.sh-conversation{position:relative;padding:7px 28px 7px 9px;border-radius:var(--r-md);cursor:pointer;color:var(--n-700);overflow:hidden;margin-bottom:2px}',
    '.sh-conversation:hover{background:var(--n-100)}',
    '.sh-conversation.active{background:var(--brand-50);color:var(--brand-strong)}',
    '.sh-conversation-title{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sh-conversation-meta{font-size:10px;color:var(--n-500);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}',
    '.sh-conversation-sub{font-size:10px;color:var(--n-400);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.sh-conversation-actions{position:absolute;right:5px;top:8px;display:none;gap:2px}',
    '.sh-conversation:hover .sh-conversation-actions{display:flex}',
    '.sh-conversation-rename,.sh-conversation-delete{border:0;background:transparent;color:var(--n-400);cursor:pointer;font-size:14px;line-height:1;padding:2px 4px;border-radius:4px}',
    '.sh-conversation-rename:hover{background:var(--n-100);color:var(--brand-strong)}',
    '.sh-conversation-delete:hover{background:#fef2f2;color:#b91c1c}',
      '@media(max-width:820px){#sh-side{display:none!important}#shell{flex-direction:column!important}#sh-center{flex:0 0 42vh!important}#sh-chat{flex:1 1 58vh!important;border-left:0!important;border-top:1px solid var(--bd-1)!important}#sh-toggle-chat{display:none!important}}'

  ].join('');

  // 图标：与 composer 同一套语言（24 网格、1.7 细线、currentColor），
  // 取代此前几何字符与彩色 emoji 的混排图标。
  function ico(paths, size) {
    var s = size || 16;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>';
  }
  var I = {
    flask: ico('<path d="M10 2v6.3L4.6 17.8A2 2 0 0 0 6.4 21h11.2a2 2 0 0 0 1.8-3.2L14 8.3V2"/><path d="M8.5 2h7"/><path d="M7.2 15h9.6"/>'),
    calc: ico('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8"/><path d="M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01"/>'),
    clipboard: ico('<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01"/>'),
    tube: ico('<path d="M14.5 2v17.5a2.5 2.5 0 0 1-5 0V2"/><path d="M8.5 2h7"/><path d="M14.5 16h-5"/>'),
    box: ico('<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="M3.3 7l8.7 5 8.7-5"/><path d="M12 22V12"/>'),
    globe: ico('<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>'),
    file: ico('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>'),
    gear: ico('<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>'),
    bell: ico('<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>')
  };

  var HTML = [
    '<div id="sh-side">',
    '  <div id="sh-brand"><span class="mark">' + ico('<path d="M10 2v6.3L4.6 17.8A2 2 0 0 0 6.4 21h11.2a2 2 0 0 0 1.8-3.2L14 8.3V2"/><path d="M8.5 2h7"/><path d="M7.2 15h9.6"/>', 15) + '</span><b>小科 · 实验助手</b></div>',
    '  <div class="sh-nav">',
    '    <div class="sh-sec">工作台</div>',
    '    <div class="sh-item active" data-view="run"><span class="sh-ico">' + I.flask + '</span><span class="sh-label">实验进行中</span></div>',
    '    <div class="sh-item" data-view="calculator"><span class="sh-ico">' + I.calc + '</span><span class="sh-label">分子量计算</span></div>',
    '    <div class="sh-item" data-view="protocols"><span class="sh-ico">' + I.clipboard + '</span><span class="sh-label">实验方案</span></div>',
    '    <div class="sh-item" data-view="reagent_prep"><span class="sh-ico">' + I.tube + '</span><span class="sh-label">试剂配置库</span></div>',
    '    <div class="sh-item" data-view="storage"><span class="sh-ico">' + I.box + '</span><span class="sh-label">储存库</span></div>',
    '    <div class="sh-item" data-view="community"><span class="sh-ico">' + I.globe + '</span><span class="sh-label">社区</span></div>',
    '    <div class="sh-item" data-view="records"><span class="sh-ico">' + I.file + '</span><span class="sh-label">本次记录</span></div>',
    '    <div class="sh-sec">配置</div>',
    '    <div class="sh-item" data-view="settings"><span class="sh-ico">' + I.gear + '</span><span class="sh-label">设置</span></div>',
    '  </div>',
    '  <div id="sh-foot"><button class="sh-btn" id="sh-collapse" style="width:100%">收起侧栏</button>',
    '  <button class="sh-btn" id="sh-skin" style="width:100%;margin-top:6px" title="纸面外观与经典外观随时互切，数据与功能完全一致"></button></div>',
    '</div>',
    '<div id="sh-center">',
    '  <div id="sh-top"><span id="sh-title">实验进行中</span>',
    '    <button class="sh-btn" id="sh-notify" type="button" title="消息通知">' + I.bell + '<span id="sh-notify-badge">0</span></button>',
    '    <div id="sh-status"></div>',
    '  </div>',
    '  <div id="sh-canvas"></div>',
    '</div>',
    '<div id="sh-chat-resizer"></div>',
    '<div id="sh-chat">',
    '  <div id="sh-conversation-panel">',
    '    <div class="sh-panel-title"><span>会话管理</span><button id="sh-close-conversation" type="button" title="关闭会话列表">✕</button></div>',
    '    <input id="sh-conversation-search" type="text" name="conversation-search-noname" placeholder="搜索会话…" autocomplete="off" spellcheck="false">',
    '    <button class="sh-btn" id="sh-new-session" type="button">＋ 新会话</button>',
    '    <div id="sh-conversation-list"></div>',
    '  </div>',
    '  <div id="sh-chat-main">',
    '    <div id="sh-chat-head"><span>实验对话</span><span id="sh-chat-actions"><button class="sh-btn" id="sh-toggle-conversation" type="button" title="显示/隐藏会话列表">会话</button><button class="sh-btn" id="sh-new-chat" type="button">新对话</button><div id="sh-more-wrap"><button class="sh-btn" id="sh-more" type="button" title="更多">⋯</button><div id="sh-more-menu" style="display:none"><button class="sh-btn" id="sh-phone" type="button">手机</button><button class="sh-btn" id="sh-call" type="button">通话</button></div></div></span></div>',
    '    <div id="sh-chat-host"></div>',
    '  </div>',
    '</div>'
  ].join('');

  function el(id) { return document.getElementById(id); }

  var VIEWS = {};
  window.shellRegisterView = function (name, render) { VIEWS[name] = render; };
  window.shellCanvas = function () { return el('sh-canvas'); };

  var current = 'chat';
  function show(view) {
    var previous = current;
    current = view;
    if (window.logAction) window.logAction('view', { view: view });
    document.body.classList.toggle('mobile-mode-chat', view === 'chat');
    document.body.classList.toggle('mobile-mode-work', view !== 'chat');
    var shell = el('shell');
    var isChat = view === 'chat';
    shell.classList.toggle('chat-view', isChat);
    // 切走设置视图时关闭设置弹窗，避免遮罩挡着其他页面
    if (view !== 'settings') {
      var settingsModal = document.getElementById('settings-modal');
      if (settingsModal) settingsModal.classList.remove('show');
    }
    Array.prototype.forEach.call(document.querySelectorAll('.sh-item'), function (n) {
      n.classList.toggle('active', n.dataset.view === view);
    });
    var titles = { chat: '智能对话', run: '实验进行中', calculator: '分子量计算', protocols: '实验方案', reagent_prep: '试剂配置库', reagents: '试剂安全库',
                   records: '本次记录', settings: '设置', storage: '储存库', community: '社区' };
    el('sh-title').textContent = titles[view] || view;
    var canvas = el('sh-canvas');
    if (previous === 'settings' && window.__settingsCleanup) window.__settingsCleanup();
    canvas.classList.remove('empty');
    var avatar = document.getElementById('assistant-avatar');
    if (avatar) avatar.classList.toggle('avatar-hidden', view !== 'run');
    if (view === 'run') {
      if (window.runCanvasRender) window.runCanvasRender(canvas);
      return;
    }
    // 聊天视图：中间是「今天这一页」。没有进行中的实验时给出人话空状态与下一步，
    // 不再显示开发者黑话「此页尚未接入」（chat 本就不是画布视图，之前落到了兜底分支）。
    if (view === 'chat') {
      canvas.innerHTML = [
        '<div class="sh-blank">',
        '  <div class="sh-blank-title">今天这一页还空着</div>',
        '  <p class="sh-blank-text">开口说话或在右边打字，记录会自动写到这一页上。<br>',
        '     想照方案做，就先翻开一个实验方案。</p>',
        '  <div class="sh-blank-acts">',
        '    <button class="sh-btn primary" data-go="protocols">翻开实验方案</button>',
        '    <button class="sh-btn" data-go="run">看实验进行中</button>',
        '  </div>',
        '</div>'
      ].join('');
      Array.prototype.forEach.call(canvas.querySelectorAll('[data-go]'), function (b) {
        b.onclick = function () { show(b.dataset.go); };
      });
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
    if (action.type === 'open_reagent_prep' && action.id) {
      if (window.prepOpenDetail) window.prepOpenDetail(action.id);
      else show('reagent_prep');
      return;
    }
    if (action.type === 'start_reagent_prep_flow' && action.id) {
      if (window.prepStartFlow) window.prepStartFlow(action.id);
      else show('reagent_prep');
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

    // 纸面皮肤：铺一层纸纹颗粒；外观切换按钮（经典外观完整保留）
    if (document.body.classList.contains('skin-paper') && !document.getElementById('paper-grain')) {
      var grain = document.createElement('div');
      grain.id = 'paper-grain';
      grain.setAttribute('aria-hidden', 'true');
      document.body.appendChild(grain);
    }
    var skinBtn = el('sh-skin');
    if (skinBtn) {
      var onPaper = document.body.classList.contains('skin-paper');
      skinBtn.textContent = onPaper ? '换回经典外观' : '换上纸面外观';
      skinBtn.onclick = function () {
        try { localStorage.setItem(SKIN_KEY, onPaper ? 'classic' : 'paper'); } catch (_) {}
        location.reload();
      };
    }

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
    var ttsButton = el('sh-tts');
    function syncTtsButton(detail) {
      if (!ttsButton) return;
      var muted = window.ttsMuted === true;
      ttsButton.textContent = muted ? '语音关闭' : '语音开启';
      ttsButton.classList.toggle('active', !muted);
      ttsButton.title = detail || (muted ? '回复语音已关闭，点击开启' : '回复语音已开启，点击关闭');
    }
    if (ttsButton) {
      syncTtsButton();
      ttsButton.onclick = function () {
        window.ttsMuted = !(window.ttsMuted === true);
        try { localStorage.setItem('tts-muted', window.ttsMuted ? '1' : '0'); } catch (_) {}
        if (window.ttsMuted) window.stopSpeech?.();
        syncTtsButton();
      };
    }
    var convoBtn = el('sh-toggle-conversation');
    if (convoBtn) {
      // 默认展开：会话列表是查历史会话的唯一入口，默认藏起来等于功能消失。
      // 2026-08-30 教训：曾因"它挡住聊天正文"改为默认收起，结果用户找不到历史会话；
      // 正解是让它不再压住正文（见 theme.css 给 #sh-chat-main 让位），而不是把它藏起来。
      var convoHidden = localStorage.getItem('lab-conversation-hidden') === '1';
      shell.classList.toggle('conversation-hidden', convoHidden);
      convoBtn.classList.toggle('active', !convoHidden);
      function setConvoHidden(hidden) {
        shell.classList.toggle('conversation-hidden', hidden);
        localStorage.setItem('lab-conversation-hidden', hidden ? '1' : '0');
        convoBtn.classList.toggle('active', !hidden);
        if (!hidden && window.conversationListReload) window.conversationListReload();
      }
      convoBtn.onclick = function () { setConvoHidden(!shell.classList.contains('conversation-hidden')); };
      var closeConvo = el('sh-close-conversation');
      if (closeConvo) closeConvo.onclick = function () { setConvoHidden(true); };
    }
    // 兜底：无论初始化是否成功，点会话管理的 ✕ 都能关闭面板
    document.addEventListener('click', function (e) {
      var close = e.target.closest('#sh-close-conversation');
      if (close) {
        shell.classList.add('conversation-hidden');
        try { localStorage.setItem('lab-conversation-hidden', '1'); } catch (_) {}
        var cvBtn = el('sh-toggle-conversation');
        if (cvBtn) cvBtn.classList.remove('active');
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && shell.classList.contains('conversation-hidden')) {
        shell.classList.remove('conversation-hidden');
        try { localStorage.setItem('lab-conversation-hidden', '0'); } catch (_) {}
        var cvBtn = el('sh-toggle-conversation');
        if (cvBtn) cvBtn.classList.add('active');
      }
    });

    var moreBtn = el('sh-more');
    var moreMenu = el('sh-more-menu');
    if (moreBtn && moreMenu) {
      moreBtn.onclick = function (e) {
        e.stopPropagation();
        var open = moreMenu.style.display === 'block';
        moreMenu.style.display = open ? 'none' : 'block';
      };
      document.addEventListener('click', function (e) {
        if (!e.target.closest('#sh-more-wrap')) moreMenu.style.display = 'none';
      });
    }

    function initChatResizer() {
      var resizer = el('sh-chat-resizer');
      var chat = el('sh-chat');
      var key = 'lab-chat-width';
      var saved = parseInt(localStorage.getItem(key), 10) || 640;
      chat.style.flex = '0 0 ' + saved + 'px';
      var startX = 0, startWidth = 0;
      resizer.addEventListener('mousedown', function (e) {
        e.preventDefault();
        startX = e.clientX;
        startWidth = chat.getBoundingClientRect().width;
        resizer.classList.add('dragging');
        document.body.style.userSelect = 'none';
        chat.style.transition = 'none';
        function move(ev) {
          var width = startWidth - (ev.clientX - startX);
          var min = 380, max = Math.min(window.innerWidth * 0.6, 900);
          width = Math.max(min, Math.min(max, width));
          chat.style.flex = '0 0 ' + Math.round(width) + 'px';
        }
        function up() {
          resizer.classList.remove('dragging');
          document.body.style.userSelect = '';
          chat.style.transition = '';
          localStorage.setItem(key, String(Math.round(chat.getBoundingClientRect().width)));
          window.removeEventListener('mousemove', move);
          window.removeEventListener('mouseup', up);
        }
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
      });
    }
    function responsive() {
      if (window.innerWidth < AUTO_COLLAPSE) shell.classList.add('side-collapsed');
    }
    initChatResizer();
    responsive();
    window.addEventListener('resize', responsive);

    document.dispatchEvent(new CustomEvent('shell-ready'));
    show('chat');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
