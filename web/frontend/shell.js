// 应用外壳：聊天时间线是唯一默认主工作区；管理页按导航整页切换。
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
    // 管理画布与聊天互斥显示，不再左右并排。
    '#sh-center{flex:1;min-width:320px;display:flex;flex-direction:column;background:var(--n-60)}',
    '#sh-top{height:44px;flex:0 0 44px;background:var(--n-00);border-bottom:1px solid var(--bd-2);display:flex;align-items:center;padding:0 14px;gap:10px}',
    '#sh-title{font-size:var(--fs-md);font-weight:600;color:var(--n-900)}',
    '#sh-status{font-size:var(--fs-sm);color:var(--n-600);margin-left:auto;display:flex;align-items:center;gap:6px}',
    '.sh-pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:var(--r-sm);background:var(--n-75);font-size:var(--fs-xs);color:var(--n-700)}',
    '.sh-pill.warn{background:var(--red-50);color:var(--red-600)}',
    '.sh-pill.ok{background:var(--green-100);color:var(--green-900)}',
    '#sh-canvas{flex:1;overflow:auto;padding:16px 20px}',
    '#sh-canvas.empty{display:flex;align-items:center;justify-content:center;color:var(--n-500);font-size:var(--fs-md);text-align:center;line-height:1.9}',
    // 唯一聊天主视图
    '#sh-chat{flex:1;background:var(--n-00);display:none;flex-direction:column;min-width:380px}',
    '#shell.chat-view #sh-center{display:none}',
    '#shell.chat-view #sh-chat{display:flex}',
    '#sh-chat-head{height:44px;flex:0 0 44px;border-bottom:1px solid var(--bd-1);display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 12px 0 16px;font-size:14px;font-weight:600;color:var(--n-800)}#sh-chat-actions{display:flex;align-items:center;gap:8px}#sh-chat-head .sh-btn{padding:4px 10px;font-size:12px;font-weight:400}',
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
      '@media(max-width:820px){#sh-side{display:none!important}#shell{flex-direction:column!important}#sh-center{min-width:0!important}#sh-chat{flex:1 1 auto!important;min-width:0!important}}'

  ].join('');

  var HTML = [
    '<div id="sh-side">',
    '  <div id="sh-brand"><span class="dot"></span><b>实验语音助手</b></div>',
    '  <div class="sh-nav">',
    '    <div class="sh-sec">工作台</div>',
    '    <div class="sh-item active" data-view="chat"><span class="sh-ico">◌</span><span class="sh-label">主对话</span></div>',
    '    <div class="sh-item" data-view="protocols"><span class="sh-ico">☰</span><span class="sh-label">实验方案</span></div>',
    '    <div class="sh-item" data-view="reagents"><span class="sh-ico">⚗</span><span class="sh-label">试剂安全库</span></div>',
    '    <div class="sh-item" data-view="records"><span class="sh-ico">▤</span><span class="sh-label">本次记录</span></div>',
    '    <div class="sh-sec">配置</div>',
    '    <div class="sh-item" data-view="settings"><span class="sh-ico">⚙</span><span class="sh-label">模型与语音</span></div>',
    '  </div>',
    '  <div id="sh-foot"><button class="sh-btn" id="sh-collapse" style="width:100%">收起侧栏</button></div>',
    '</div>',
    '<div id="sh-center">',
    '  <div id="sh-top"><span id="sh-title">实验方案</span>',
    '    <div id="sh-status"></div>',
    '  </div>',
    '  <div id="sh-canvas"></div>',
    '</div>',
    '<div id="sh-chat">',
    '  <div id="sh-chat-head"><span>实验对话</span><span id="sh-chat-actions"><button class="sh-btn" id="sh-tts" type="button" title="开启或关闭回复语音">语音开启</button><button class="sh-btn" id="sh-phone" type="button">手机</button><button class="sh-btn" id="sh-new-chat" type="button">新对话</button></span></div>',
    '  <div id="sh-chat-host"></div>',
    '</div>'
  ].join('');

  function el(id) { return document.getElementById(id); }

  var VIEWS = {};
  window.shellRegisterView = function (name, render) { VIEWS[name] = render; };
  window.shellCanvas = function () { return el('sh-canvas'); };

  var current = 'chat';
  function show(view) {
    current = view;
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
    if (isChat) return;
    var titles = { protocols: '实验方案', reagents: '试剂安全库',
                   records: '本次记录', settings: '模型与语音' };
    el('sh-title').textContent = titles[view] || view;
    var canvas = el('sh-canvas');
    canvas.classList.remove('empty');
    canvas.innerHTML = '<div style="color:#94a3b8;font-size:13px">加载中…</div>';
    if (VIEWS[view]) VIEWS[view](canvas);
    else canvas.innerHTML = '<div style="color:#94a3b8;font-size:13px">此页尚未接入</div>';
  }
  window.shellShow = show;
  window.shellCurrentView = function () { return current; };
  window.shellStatus = function (html) { el('sh-status').innerHTML = html; };

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
    var ttsButton = el('sh-tts');
    function syncTtsButton(detail) {
      var muted = window.ttsMuted === true;
      ttsButton.textContent = muted ? '语音关闭' : '语音开启';
      ttsButton.classList.toggle('active', !muted);
      ttsButton.title = detail || (muted ? '回复语音已关闭，点击开启' : '回复语音已开启，点击关闭');
    }
    syncTtsButton();
    ttsButton.onclick = function () {
      window.ttsMuted = !(window.ttsMuted === true);
      try { localStorage.setItem('tts-muted', window.ttsMuted ? '1' : '0'); } catch (_) {}
      if (window.ttsMuted) window.stopSpeech?.();
      syncTtsButton();
    };
    window.addEventListener('voice-delivery-result', function (event) {
      var code = event.detail && event.detail.code;
      var labels = {
        PLAYED: '已提交语音播放', PLAYBACK_DISABLED: '语音开关已关闭',
        REJECTED_PAYLOAD: '语音来源校验失败', TTS_UNAVAILABLE: '语音播放器不可用'
      };
      syncTtsButton(labels[code]);
    });

    function responsive() {
      if (window.innerWidth < AUTO_COLLAPSE) shell.classList.add('side-collapsed');
    }
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
