// 对话输入区（composer）：对齐 deepseek-harness 的 InputBar 规格。
//   卡片圆角 22px，边框 rgba(0,0,0,.10)，textarea 16px/24px，
//   textarea 与控制行间距 12px，卡片顶部内边距 10px，控制行 padding 2px 8px 6px。
// 结构上是「一张卡片包住输入框 + 控制行」，而不是输入框和按钮各自为政。
(function () {
  var autoProtocolApplied = false;
  var CSS = [
    '#cp-wrap{padding:0 16px 10px;background:var(--n-00);flex:0 0 auto}',
    '#cp-card{box-sizing:border-box;position:relative;display:flex;flex-direction:column;gap:5px;',
    '  width:100%;padding:14px 8px 8px;border:1px solid rgba(0,0,0,.10);border-radius:22px;',
    '  background:var(--n-00);box-shadow:0 1px 2px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.05)}',
    '#cp-card.focus{border-color:rgba(0,0,0,.16)}',
    '#cp-text{border:0;outline:0;resize:none;width:100%;box-sizing:border-box;padding:2px 10px 0;',
    '  font-size:15px;line-height:23px;font-family:inherit;color:var(--n-900);background:transparent;',
    '  max-height:168px;overflow-y:auto}',
    '#cp-text::placeholder{color:var(--n-400)}',
    '#cp-row{display:flex;align-items:center;justify-content:flex-start;gap:10px;padding:4px 6px 0;min-width:0;flex-wrap:wrap}',
    '.cp-left{display:flex;align-items:center;gap:7px;min-width:0;flex-wrap:nowrap;flex:0 0 auto}',
    '.cp-right{display:flex;align-items:center;gap:7px;min-width:0;flex-wrap:wrap;row-gap:6px;flex:1 1 auto;justify-content:flex-end;margin-left:auto}',
    '.cp-actions,.cp-tail{display:inline-flex;align-items:center;gap:7px;min-width:0;flex-wrap:wrap;row-gap:6px;flex:0 0 auto}',
    '.cp-tail{margin-left:auto}',
    '.cp-icon{width:30px;height:30px;border-radius:50%;border:1px solid rgba(0,0,0,.10);background:var(--n-00);',
    '  color:var(--n-600);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:15px;flex:0 0 auto;font-family:inherit}',
    '.cp-icon:hover{background:var(--n-60)}',
    '.cp-icon.rec{background:var(--red-500);border-color:var(--red-500);color:#fff}',
    '.cp-icon.wake{background:var(--brand-50);border-color:var(--brand);color:var(--brand)}',
    '.cp-icon.active{background:var(--brand);border-color:var(--brand);color:#fff;box-shadow:0 0 0 3px rgba(37,99,235,.18)}',
    '.cp-chip{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 10px;border-radius:15px;',
    '  border:1px solid rgba(0,0,0,.10);background:var(--n-00);color:var(--n-700);font-size:var(--fs-sm);',
    '  cursor:pointer;white-space:nowrap;font-family:inherit;max-width:190px;overflow:hidden;text-overflow:ellipsis;flex:0 0 auto}',
    '.cp-chip:hover{background:var(--n-60)}',
    '.cp-chip .v{color:var(--n-500)}',
    '.cp-chip.plain{border:0;background:transparent;padding:0 4px;cursor:default}',
    '.cp-chip.perm{font-size:12px;height:28px;border-radius:14px}',
    '.cp-chip.perm svg{color:var(--brand)}',
    '.cp-chip.mode{font-size:12px;height:28px;border-radius:14px}',
    '.cp-chip.mode svg{color:var(--brand)}',
    '#cp-continuous-label{display:inline-flex;align-items:center;gap:5px;color:var(--n-700);font-size:var(--fs-xs);white-space:nowrap;cursor:pointer}',
    '#cp-continuous{margin:0;accent-color:var(--brand)}',
    '#cp-modes{display:flex;align-items:center;gap:2px;padding:3px;border-radius:16px;background:var(--n-60);flex-wrap:nowrap;overflow-x:auto;max-width:56vw}',
    '.cp-mode{border:0;border-radius:13px;padding:5px 9px;background:transparent;color:var(--n-600);cursor:pointer;font:inherit;font-size:var(--fs-xs);white-space:nowrap}',
    '.cp-mode.active{background:var(--n-00);color:var(--brand);box-shadow:0 1px 3px rgba(0,0,0,.10)}',
    '#cp-send{width:32px;height:32px;border-radius:50%;border:0;background:var(--brand);color:#fff;',
    '  cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:15px;flex:0 0 auto}',
    '#cp-send:hover{background:var(--brand-strong)}',
    '#cp-send:disabled{background:var(--n-200);color:var(--n-500);cursor:not-allowed}',
    '#cp-icon-help{width:26px;height:26px;border-radius:50%;border:1px solid rgba(0,0,0,.10);background:var(--n-00);color:var(--n-500);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:13px;flex:0 0 auto;font-family:inherit}',
    '#cp-icon-help:hover{background:var(--n-60);color:var(--n-800)}',
    '#cp-voice-intro{position:fixed;inset:0;background:rgba(15,23,42,.5);display:none;align-items:center;justify-content:center;z-index:9999;padding:20px}',
    '#cp-voice-intro.show{display:flex}',
    '.cp-voice-box{background:#fff;border-radius:18px;max-width:560px;width:100%;max-height:86vh;overflow:auto;padding:22px 26px;box-shadow:0 24px 60px rgba(15,23,42,.25)}',
    '.cp-voice-box h2{margin:0 0 4px;font-size:18px;color:#0f172a}',
    '.cp-voice-box .sub{color:#64748b;font-size:13px;margin-bottom:16px;line-height:1.7}',
    '.cp-voice-item{display:flex;gap:12px;padding:14px 0;border-top:1px solid #eef2f7;align-items:flex-start}',
    '.cp-voice-item:first-of-type{border-top:0}',
    '.cp-voice-item .ic{width:36px;height:36px;flex:0 0 36px;border-radius:12px;background:#eef2f7;display:flex;align-items:center;justify-content:center;color:#334155}',
    '.cp-voice-item b{font-size:14px;color:#0f172a;display:block}',
    '.cp-voice-item p{margin:3px 0 0;color:#64748b;font-size:13px;line-height:1.7}',
    '.cp-voice-close{margin-top:18px;text-align:right}',
    '#cp-meta .sep{color:var(--n-200)}',
    '.cp-context-ring{display:inline-block;width:15px;height:15px;border-radius:50%;flex:0 0 15px;background:conic-gradient(var(--brand) 0deg,var(--brand) 0deg,var(--n-200) 0deg)}',
    // 下拉面板
    '#cp-pop{position:absolute;bottom:44px;right:8px;background:var(--n-00);border:1px solid rgba(0,0,0,.10);',
    '  border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.12);min-width:250px;padding:5px;display:none;z-index:30}',
    '#cp-pop.on{display:block}',
    '#cp-mode-pop{position:absolute;bottom:44px;left:8px;background:var(--n-00);border:1px solid rgba(0,0,0,.10);',
    '  border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.12);min-width:240px;padding:5px;display:none;z-index:30}',
    '#cp-mode-pop.on{display:block}',
    '#cp-model-pop{position:absolute;bottom:44px;right:8px;background:var(--n-00);border:1px solid rgba(0,0,0,.10);',
    '  border-radius:14px;box-shadow:0 14px 40px rgba(0,0,0,.14);min-width:320px;max-width:420px;display:none;z-index:30;overflow:hidden}',
    '#cp-model-pop.on{display:block}',
    '.cp-model-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--bd-1);font-size:13px;font-weight:600;color:var(--n-800)}',
    '.cp-model-close{border:0;background:transparent;color:var(--n-400);font-size:14px;cursor:pointer}',
    '#cp-model-list{max-height:300px;overflow:auto;padding:5px}',
    '.cp-model-row{display:flex;align-items:center;gap:9px;padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--n-700)}',
    '.cp-model-row:hover{background:var(--n-60)}',
    '.cp-model-row.active{background:var(--brand-50);color:var(--brand-strong)}',
    '.cp-model-row .m-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.cp-model-row .m-meta{color:var(--n-400);font-size:11px;white-space:nowrap}',
    '.cp-model-row .m-check{color:var(--brand);font-size:13px}',
    '.cp-model-custom{display:block;width:100%;padding:10px 12px;border:0;border-top:1px solid var(--bd-1);background:transparent;color:var(--brand-strong);font-size:12px;cursor:pointer;text-align:left}',
    '.cp-model-custom:hover{background:var(--n-60)}',
    '.cp-mode-pop-row{display:block;padding:8px 11px;border-radius:8px;font-size:var(--fs-sm);color:var(--n-800);cursor:pointer}',
    '.cp-mode-pop-row:hover{background:var(--n-60)}',
    '.cp-mode-pop-row.active{background:var(--brand-50);color:var(--brand-strong)}',
    '.cp-mode-pop-row em{display:block;font-style:normal;font-size:var(--fs-xs);color:var(--n-500);margin-top:2px}',
    '.cp-pop-row{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;font-size:var(--fs-md);color:var(--n-800);cursor:pointer}',
    '.cp-pop-row:hover{background:var(--n-60)}',
    '.cp-pop-row .k{flex:0 0 auto}',
    '.cp-pop-row .v{margin-left:auto;color:var(--n-500);display:flex;align-items:center;gap:4px}',
    '.cp-pop-row .chev{color:var(--n-400);font-size:11px}',
    '.cp-phone-pop{position:fixed;left:50%;transform:translateX(-50%);bottom:84px;background:transparent;display:flex;align-items:center;justify-content:center;z-index:60;pointer-events:none}',
    '.cp-phone-pop-box{background:var(--n-00);border-radius:16px;box-shadow:0 18px 60px rgba(0,0,0,.24);max-width:400px;width:calc(100vw - 40px);padding:12px 14px 16px;pointer-events:auto}',
    '.cp-phone-pop-head{display:flex;align-items:center;justify-content:space-between;font-size:14px;font-weight:600;color:var(--n-900);padding-bottom:8px}',
    '.cp-phone-pop-head button{border:0;background:transparent;color:var(--n-400);font-size:16px;cursor:pointer}',
    '.cp-phone-pop .qr-wrap{margin:6px auto 10px;width:230px;height:230px;display:flex;align-items:center;justify-content:center;border:1px solid var(--bd-1);border-radius:12px;background:#fff}',
    '.cp-phone-pop .qr-wrap svg{width:210px;height:210px;display:block}',
    '.cp-phone-pop .phone-link{font-size:12px;color:var(--brand-strong);word-break:break-all;padding:0 8px}',
    // 手机图标旁的“小箭头”：隧道已开时用来单独查看二维码，不影响主按钮的开关逻辑。
    '#cp-phone-qr{display:none;align-items:center;justify-content:center;width:18px;height:26px;border:0;',
    '  background:transparent;color:var(--n-400);cursor:pointer;font-size:12px;padding:0;flex:0 0 auto;',
    '  line-height:1;border-radius:6px;margin-left:-5px}',
    '#cp-phone-qr.on{display:inline-flex}',
    '#cp-phone-qr:hover{color:var(--brand);background:var(--n-60)}'
  ].join('');

  var ICONS = {
    plus: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>',
    mic: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><path d="M12 18v4"/></svg>',
    phoneCall: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.09 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
    wake: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0-6 6v3l-2 3h16l-2-3V9a6 6 0 0 0-6-6z"/><path d="M10 19h4"/></svg>',
    phone: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M12 18h.01"/></svg>',
    realtime: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2 11h2M5 7v8M8 4v16M11 8v8M14 6v12M17 9v6M20 12h2"/></svg>',
    stop: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m8 12 2.5 2.5L16 9.5"/></svg>',
    robot: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="8" width="16" height="11" rx="2"/><path d="M12 8V4"/><circle cx="9" cy="13" r="1"/><circle cx="15" cy="13" r="1"/><path d="M9 16h6"/></svg>',
    layers: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 8.5 4.5-8.5 4.5L3.5 6.5 12 2Z"/><path d="m3.5 12 8.5 4.5 8.5-4.5"/><path d="m3.5 17.5 8.5 4.5 8.5-4.5"/></svg>'
  };

  var HTML = [
    '<div id="cp-card">',
    '  <textarea id="cp-text" rows="1" placeholder="给实验助手发消息，或按住麦克风口述"></textarea>',
    '  <div id="cp-row">',
    '    <div class="cp-left">',
    '      <button class="cp-icon" id="cp-file" title="上传文件">' + ICONS.plus + '</button>',
    '      <input type="file" id="cp-file-input" style="display:none" />',
    '      <button class="cp-chip mode" id="cp-mode" title="切换交互模式">' + ICONS.layers + '<span id="cp-mode-name">方案实验</span><span class="v">⌄</span></button>',
    '    </div>',
    '    <div class="cp-right">',
    '      <span class="cp-actions">',
    '      <button class="cp-icon" id="cp-icon-help" title="语音/通信功能介绍" style="width:26px;height:26px;font-size:13px">?</button>',
    '      <button class="cp-icon" id="cp-realtime-voice" title="实时语音：Qwen Audio 全双工，直接使用实验助手后台">' + ICONS.realtime + '</button>',
    '      <button class="cp-icon" id="cp-phone-call" title="和小科通话：连续对话，说话可打断；再点一次挂断">' + ICONS.phoneCall + '</button>',
    '      <button class="cp-icon" id="cp-phone" title="手机扫码使用">' + ICONS.phone + '</button>',
    '      <button id="cp-phone-qr" title="查看二维码/公网地址（不关闭隧道）">⌄</button>',
    '      <button class="cp-icon" id="cp-mic" title="录一段话：点一下开始，再点一下结束">' + ICONS.mic + '</button>',
    '      </span>',
    '      <span class="cp-tail">',
    '      <button class="cp-chip" id="cp-model"><span id="cp-model-name">未配置模型</span><span class="v">⌄</span></button>',
    '      <button id="cp-send" title="发送">↑</button>',
    '      </span>',
    '    </div>',
    '  </div>',
    '  <div id="cp-model-pop">',
    '    <div class="cp-model-head"><span>选择模型</span><button class="cp-model-close" id="cp-model-close" title="关闭">✕</button></div>',
    '    <div id="cp-thinking-row" style="display:none;padding:8px 12px;border-bottom:1px solid var(--bd-1);align-items:center;justify-content:space-between">',
    '      <span style="font-size:12px;color:var(--n-600)">思考程度</span>',
    '      <select id="cp-thinking-level" style="padding:4px 8px;border:1px solid var(--bd-2);border-radius:8px;font-size:12px;background:var(--n-00)">',
    '        <option value="auto">自动</option><option value="disabled">关闭</option>',
    '        <option value="low">低</option><option value="medium">中</option><option value="high">高</option>',
    '      </select>',
    '    </div>',
    '    <div id="cp-model-list"></div>',
    '    <button class="cp-model-custom" id="cp-model-custom">配置自定义模型</button>',
    '  </div>',
    '  <span id="cp-hint" style="display:none"></span>',
    '  <div id="cp-mode-pop">',
    '    <div class="cp-mode-pop-row" data-mode="protocol"><span>方案实验</span><em>按当前方案逐步推进并记录</em></div>',
    '    <div class="cp-mode-pop-row" data-mode="template"><span>AI制作方案/配方</span><em>对话创建或修改；PDF/图片请到方案页导入</em></div>',
    '    <div class="cp-mode-pop-row" data-mode="storage"><span>制作储存库</span><em>登记位置/物品/库存</em></div>',
    '  </div>',
    '</div>',
    '<div id="cp-meta"></div>',
    '<div id="cp-voice-intro">',
    '  <div class="cp-voice-box">',
    '    <h2>语音 / 通信功能介绍</h2>',
    '    <div class="sub">这里四个按钮分别对应不同语音方式，按需选择即可。</div>',
    '    <div class="cp-voice-item"><div class="ic">▥▥</div><div><b>实时语音（推荐）</b><p>Qwen Audio 全双工，可随时打断；背后走实验助手后台，适合边做实验边说。</p></div></div>',
    '    <div class="cp-voice-item"><div class="ic">☎</div><div><b>和小科通话</b><p>原来的 DeepSeek 连续通话，点一下开始、再点一下挂断，说话可打断。</p></div></div>',
    '    <div class="cp-voice-item"><div class="ic">▯</div><div><b>手机扫码</b><p>打开手机扫码页，用手机浏览器进入控制，适合离开电脑时使用。</p></div></div>',
    '    <div class="cp-voice-item"><div class="ic">🎤</div><div><b>麦克风（可选）</b><p>单次录音：点一下开始、再点一下结束。适合偶尔只录一句话，已有实时语音可以少用。</p></div></div>',
    '    <div class="cp-voice-close"><button class="sh-btn primary" id="cp-voice-intro-close" type="button">知道了</button></div>',
    '  </div>',
    '</div>',
    '<div id="cp-phone-pop" class="cp-phone-pop" style="display:none">',
    '  <div class="cp-phone-pop-box">',
    '    <div class="cp-phone-pop-head"><span>手机访问</span><button id="cp-phone-pop-close" title="关闭">✕</button></div>',
    '    <div id="cp-phone-pop-body" style="text-align:center;padding:6px 8px 14px">加载中…</div>',
    '  </div>',
    '</div>'
  ].join('');

  function el(id) { return document.getElementById(id); }

  function currentModeLabel(protocolSession) {
    var snapshot = window.interactionModeState?.capture('text');
    if (!snapshot || snapshot.interaction_mode === 'chat') return '自由聊天';
    if (snapshot.experiment_context === 'free') return '自由实验记录';
    if (snapshot.experiment_context === 'protocol') {
      return protocolSession && protocolSession.mode === 'protocol' && protocolSession.protocol
        ? protocolSession.protocol.title + ' 第' + protocolSession.step.number + '步'
        : '方案实验';
    }
    if (snapshot.experiment_context === 'template') return '模板实验';
    if (snapshot.experiment_context === 'storage') return '实验存储';
    return '实验模式';
  }
  window.composerCurrentModeLabel = currentModeLabel;

  var stats = { turns: 0, tools: 0, seconds: 0, chars: 0 };

  function renderMeta() {
    var bits = [];
    bits.push(stats.turns + ' 轮');
    if (stats.tools) bits.push(stats.tools + ' 次工具调用');
    if (stats.seconds) bits.push('累计 ' + stats.seconds.toFixed(1) + 's');
    if (stats.chars) bits.push('输出 ' + stats.chars + ' 字');
    el('cp-meta').innerHTML = bits.join(' <span class="sep">|</span> ');
  }
  window.composerStat = function (patch) {
    Object.keys(patch || {}).forEach(function (k) { stats[k] = (stats[k] || 0) + patch[k]; });
    renderMeta();
  };

  // 上传物 = 夹进本子的附页：文件是回形针别着的纸条，图片是贴上去的白边照片。
  // 纯前端呈现，落盘与后续处理仍走原有 /api/upload + composerSend 链路。
  function humanSize(bytes) {
    var n = Number(bytes) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1024 / 1024).toFixed(1) + ' MB';
  }
  function addAttachment(file, meta) {
    var chat = document.querySelector('#chat');
    if (!chat) return;
    var isImage = /^image\//.test(file.type || '');
    var row = document.createElement('div');
    row.className = 'message user attach-row';
    var box = document.createElement('div');
    box.className = 'attach' + (isImage ? ' attach-photo' : ' attach-file');
    var name = String(meta && meta.name || file.name || '附件');
    if (isImage) {
      var url = URL.createObjectURL(file);
      var img = document.createElement('img');
      img.src = url;
      img.alt = name;
      img.onload = function () { URL.revokeObjectURL(url); };
      box.appendChild(img);
      var cap = document.createElement('div');
      cap.className = 'attach-cap';
      cap.textContent = name;
      box.appendChild(cap);
    } else {
      box.innerHTML = '<span class="clip" aria-hidden="true">'
        + '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M21.4 11.05 12.3 20.1a5.5 5.5 0 0 1-7.8-7.78l9.2-9.2a3.7 3.7 0 0 1 5.2 5.2l-9.1 9.1a1.8 1.8 0 0 1-2.6-2.6l8.5-8.4"/></svg></span>'
        + '<span class="attach-name"></span><span class="attach-meta"></span>';
      box.querySelector('.attach-name').textContent = name;
      box.querySelector('.attach-meta').textContent = humanSize(meta && meta.size || file.size);
    }
    row.appendChild(box);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
  }

  function autoGrow() {
    var box = el('cp-text');
    box.style.height = 'auto';
    box.style.height = Math.min(168, box.scrollHeight) + 'px';
  }

  function send(options) {
    var box = el('cp-text');
    var text = box.value.trim();
    if (!text) return;
    if (window.logAction) window.logAction('composer_send', { text: text.slice(0, 80), inputSource: (options && options.inputSource) || 'text' });
    var input = document.querySelector('#message');
    var form = document.querySelector('#form');
    if (!input || !form) return;
    window.captureComposerModeSnapshot(
      form, (options && options.inputSource) || 'text', options && options.modeSnapshot
    );
    input.value = text;
    box.value = '';
    autoGrow();
    stats.turns += 1;
    renderMeta();
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
  window.composerSend = function (text, options) {
    el('cp-text').value = text;
    send(options);
  };

  function refresh() {
    fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
      var name = d.ready ? d.settings.model_name : '未配置模型';
      el('cp-model-name').textContent = name;
      el('cp-send').disabled = !d.ready;
    }).catch(function () {});
    var protocolPath = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session')
      : '/protocols/session';
    fetch(protocolPath).then(function (r) { return r.json(); }).then(function (d) {
      var protoEl = el('cp-pop-proto');
      if (protoEl) protoEl.innerHTML = currentModeLabel(d) + '<span class="chev">›</span>';
    }).catch(function () {});
  }
  window.composerRefresh = refresh;

  function selectComposerMode(mode) {
    if (mode === 'free') {
      return fetch('/protocols/session', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({protocol_id: null})
      }).then(function (response) {
        if (!response.ok) throw new Error('退出方案模式失败');
        return response.json();
      }).then(function (session) {
        if (session.mode !== 'free') throw new Error('服务端没有进入自由记录模式');
        window.interactionModeState.select('free');
        refresh();
        return true;
      }).catch(function (error) {
        var hint = el('cp-hint');
        if (hint) hint.textContent = error.message;
        return false;
      });
    }
    if (mode !== 'protocol') {
      window.interactionModeState.select(mode);
      return Promise.resolve(true);
    }
    return fetch('/protocols/session').then(function (response) {
      if (!response.ok) throw new Error('方案会话读取失败');
      return response.json();
    }).then(function (session) {
      if (session.mode !== 'protocol' || !session.protocol) {
        if (window.shellShow) window.shellShow('protocols');
        return false;
      }
      window.interactionModeState.select('protocol', session.protocol.id);
      return true;
    }).catch(function () {
      if (window.shellShow) window.shellShow('protocols');
      return false;
    });
  }
  window.selectComposerMode = selectComposerMode;

  function init() {
    var host = document.getElementById('sh-chat-main') || document.getElementById('sh-chat');
    if (!host) { setTimeout(init, 300); return; }

    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var wrap = document.createElement('div');
    wrap.id = 'cp-wrap';
    wrap.innerHTML = HTML;
    host.appendChild(wrap);

    // 队友原来的输入行与语音条由 composer 取代，隐藏但保留节点（事件仍绑在上面）
    var oldForm = document.querySelector('.chat-form');
    if (oldForm) oldForm.style.display = 'none';
    var oldVoice = document.querySelector('.voice-row');
    if (oldVoice) oldVoice.style.display = 'none';
    var asrBar = document.getElementById('asr-bar');
    if (asrBar) asrBar.style.display = 'none';

    var box = el('cp-text');
    box.addEventListener('input', autoGrow);
    box.addEventListener('focus', function () { el('cp-card').classList.add('focus'); });
    box.addEventListener('blur', function () { el('cp-card').classList.remove('focus'); });
    var fileBtn = el('cp-file');
    var fileInput = el('cp-file-input');
    if (fileBtn && fileInput) {
      fileBtn.onclick = function () { fileInput.click(); };
      fileInput.onchange = function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) return;
        var form = new FormData();
        form.append('file', file);
        // 用 class 表达"上传中"，不写 textContent——那会把 SVG 图标顶掉且再也变不回来。
        fileBtn.classList.add('busy');
        fileBtn.disabled = true;
        function restore() { fileBtn.classList.remove('busy'); fileBtn.disabled = false; }
        fetch('/api/upload', { method: 'POST', body: form }).then(function (r) {
          return r.json().then(function (d) { return { ok: r.ok, d: d }; });
        }).then(function (res) {
          restore();
          if (!res.ok) { alert(res.d.detail || '上传失败'); return; }
          if (window.logAction) window.logAction('file_upload', { name: res.d.name, size: res.d.size });
          addAttachment(file, res.d);
          window.composerSend('请读取并处理我上传的文件：file_id=' + res.d.file_id + '，文件名为 ' + res.d.name);
        }).catch(function (e) { restore(); alert('上传失败：' + e.message); });
      };
    }

    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    el('cp-send').onclick = send;

    // 麦克风只决定 input_source；Chat 转回聊天，实验模式才进入 /record。
    // 图标用 innerHTML 换 SVG（录音中=停止方块），不再用 textContent 写字符——
    // 那会把 SVG 图标整个顶掉，切一次录音/通话图标就永久变回字符。
    var continuousActive = false;
    function showRecordingState(active) {
      if (continuousActive) return;
      el('cp-mic').classList.toggle('rec', active);
      el('cp-mic').innerHTML = active ? ICONS.stop : ICONS.mic;
      el('cp-hint').textContent = active ? '正在录音，再点一次结束' : '单次录音';
    }
    document.addEventListener('lab:recording-state', function (event) {
      showRecordingState(Boolean(event.detail && event.detail.recording));
    });
    // 通话状态属于通话按钮（cp-phone-call 变红），不再占用麦克风按钮表达。
    document.addEventListener('lab:continuous-call-state', function (event) {
      continuousActive = Boolean(event.detail && event.detail.active);
      el('cp-mic').classList.remove('rec');
      el('cp-mic').innerHTML = ICONS.mic;
      el('cp-hint').textContent = continuousActive ? '通话中，直接说话' : '单次录音';
    });
    el('cp-mic').onclick = function () {
      var real = document.getElementById('asr-btn');
      if (!real || real.disabled) return;
      real.click();
    };
    var phoneCallBtn = el('cp-phone-call');
    if (phoneCallBtn) phoneCallBtn.onclick = function () { if (window.logAction) window.logAction('phone_call_toggle'); window.phoneCallToggle?.(); };
    var wakeWordBtn = el('cp-wake-word');
    if (wakeWordBtn) wakeWordBtn.onclick = function () { if (window.logAction) window.logAction('wake_word_toggle'); window.wakeWordToggle?.(); };
    document.addEventListener('lab:wake-word-state', function (event) {
      var waiting = Boolean(event.detail && event.detail.waiting);
      wakeWordBtn?.classList.toggle('wake', waiting);
      wakeWordBtn?.setAttribute('aria-pressed', waiting ? 'true' : 'false');
    });
    var phoneBtn = el('cp-phone');
    if (phoneBtn) phoneBtn.onclick = function () { if (window.logAction) window.logAction('open_phone_page'); window.open('/phone', '_blank'); };

    // 模型：直接进入模型设置页（选择模型/API/供应商）
    el('cp-model').onclick = function (e) {
      e.stopPropagation();
      if (window.logAction) window.logAction('open_settings');
      if (window.shellShow) window.shellShow('settings');
    };
    var popMenu = el('cp-pop');  // cp-pop 已被 cp-mode-pop 取代，可能不存在
    if (popMenu) {
      document.addEventListener('click', function () { popMenu.classList.remove('on'); });
      popMenu.onclick = function (e) { e.stopPropagation(); };
      Array.prototype.forEach.call(popMenu.querySelectorAll('.cp-pop-row'), function (row) {
        row.onclick = function () {
          popMenu.classList.remove('on');
          if (window.shellShow) window.shellShow(row.dataset.go);
        };
      });
    }
    var realtimeBtn = el('cp-realtime-voice');
    if (realtimeBtn) {
      realtimeBtn.onclick = function () {
        if (window.logAction) window.logAction('toggle_realtime_voice');
        if (typeof window.realtimeVoiceToggle === 'function') {
          window.realtimeVoiceToggle();
        } else {
          if (window.shellShow) window.shellShow('run');
        }
      };
      var syncRealtimeActive = function () {
        var on = window.__realtimeVoiceActive === true;
        realtimeBtn.classList.toggle('active', on);
      };
      syncRealtimeActive();
      document.addEventListener('lab:realtime-voice-state', function (event) {
        var enabled = Boolean(event.detail && event.detail.enabled);
        realtimeBtn.classList.toggle('active', enabled);
      });
      window.addEventListener('storage', function () { syncRealtimeActive(); });
      setInterval(syncRealtimeActive, 800);
    }
    var phonePop = document.getElementById('cp-phone-pop');
    var phonePopBody = document.getElementById('cp-phone-pop-body');
    var phoneQrBtn = el('cp-phone-qr');
    var phonePollTimer = null;
    var phoneTunnelActive = false;

    function syncPhoneButton() {
      if (phoneBtn) phoneBtn.classList.toggle('active', phoneTunnelActive);
      if (phoneQrBtn) phoneQrBtn.classList.toggle('on', phoneTunnelActive);
    }

    function setPhonePopBody(html) {
      if (phonePopBody) phonePopBody.innerHTML = html;
    }

    function showPhoneQr() {
      setPhonePopBody('加载中…');
      fetch('/phone/qr').then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) {
          if (d.reason && d.reason.indexOf('公网隧道未开启') >= 0) {
            startPublicTunnel();
            return;
          }
          setPhonePopBody('<div style="color:#c2410c;font-size:13px;padding:16px">' + (d.reason || '公网地址不可用') + '</div>');
          return;
        }
        var qr = d.qr_svg ? '<div class="qr-wrap">' + d.qr_svg + '</div>'
          : '<div class="qr-wrap" style="font-size:12px;color:#64748b">二维码生成失败</div>';
        var url = d.url || d.display_url || '';
        phoneTunnelActive = true;
        syncPhoneButton();
        setPhonePopBody(qr
          + '<div style="font-size:12px;color:#64748b;margin-top:4px">手机扫码后自动登录（公网 HTTPS）</div>'
          + '<div style="font-size:11px;color:#94a3b8;margin-top:2px">扫码自动登录，长期有效；同一二维码可重复使用。</div>'
          + '<div class="phone-link"><a href="' + url + '" target="_blank" rel="noopener">' + (d.display_url || url) + '</a></div>');
      }).catch(function (e) {
        setPhonePopBody('加载失败：' + e.message);
      });
    }

    function startPublicTunnel() {
      phoneTunnelActive = true;
      syncPhoneButton();
      setPhonePopBody('<div style="font-size:13px;color:#334155;padding:18px">正在开启公网隧道，约需十几秒…</div>');
      fetch('/network/mode', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'tunnel' }),
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) {
            phoneTunnelActive = false;
            syncPhoneButton();
            setPhonePopBody('<div style="color:#c2410c;font-size:13px;padding:16px">' + (res.d.detail || '开启公网隧道失败') + '</div>');
            return;
          }
          pollTunnelStatus();
        }).catch(function (e) {
          phoneTunnelActive = false;
          syncPhoneButton();
          setPhonePopBody('开启失败：' + e.message);
        });
    }

    function stopPublicTunnel() {
      setPhonePopBody('<div style="font-size:13px;color:#334155;padding:18px">正在关闭公网隧道…</div>');
      if (phonePollTimer) { clearTimeout(phonePollTimer); phonePollTimer = null; }
      fetch('/network/mode', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'lan' }),
      }).then(function (r) { return r.json(); }).then(function (res) {
        phoneTunnelActive = false;
        syncPhoneButton();
        if (phonePop) phonePop.style.display = 'none';
      }).catch(function () {
        phoneTunnelActive = false;
        syncPhoneButton();
        if (phonePop) phonePop.style.display = 'none';
      });
    }

    function pollTunnelStatus() {
      if (!phonePop || phonePop.style.display === 'none') { if (phonePollTimer) clearTimeout(phonePollTimer); return; }
      fetch('/network/status').then(function (r) { return r.json(); }).then(function (s) {
        if (s.state === 'running' && s.public_url) {
          if (phonePollTimer) clearTimeout(phonePollTimer);
          phoneTunnelActive = true;
          syncPhoneButton();
          showPhoneQr();
          return;
        }
        if (s.state === 'error') {
          if (phonePollTimer) clearTimeout(phonePollTimer);
          phoneTunnelActive = false;
          syncPhoneButton();
          setPhonePopBody('<div style="color:#c2410c;font-size:13px;padding:16px">' + (s.error || '公网隧道启动失败') + '</div>');
          return;
        }
        setPhonePopBody('<div style="font-size:13px;color:#334155;padding:18px">公网隧道正在启动，请稍候…</div>');
        if (phonePollTimer) clearTimeout(phonePollTimer);
        phonePollTimer = setTimeout(pollTunnelStatus, 1200);
      }).catch(function (e) {
        if (phonePollTimer) clearTimeout(phonePollTimer);
        setPhonePopBody('状态查询失败：' + e.message);
      });
    }

    function openPhonePop() {
      if (!phonePop) return;
      if (phoneTunnelActive) {
        stopPublicTunnel();
        return;
      }
      phonePop.style.display = 'flex';
      showPhoneQr();
    }
    if (phonePop) {
      document.getElementById('cp-phone-pop-close').onclick = function () {
        phonePop.style.display = 'none';
        if (phonePollTimer) { clearTimeout(phonePollTimer); phonePollTimer = null; }
      };
      phonePop.addEventListener('click', function (e) { if (e.target === phonePop) phonePop.style.display = 'none'; });
    }
    if (phoneBtn) phoneBtn.onclick = function () {
      if (window.logAction) window.logAction('toggle_public_phone');
      openPhonePop();
    };
    // 小箭头：隧道已开时单独查看二维码/公网地址，不影响“再点主按钮=关闭”的开关逻辑。
    if (phoneQrBtn) phoneQrBtn.onclick = function (event) {
      if (event) { event.preventDefault(); event.stopPropagation(); }
      if (!phoneTunnelActive) return;
      if (phonePop) phonePop.style.display = 'flex';
      showPhoneQr();
    };
    // 页面加载时同步已有隧道状态
    fetch('/network/status').then(function (r) { return r.json(); }).then(function (s) {
      phoneTunnelActive = s.state === 'running' && !!s.public_url;
      syncPhoneButton();
    }).catch(function () {});
    var helpBtn = el('cp-icon-help');
    var voiceIntro = document.getElementById('cp-voice-intro');
    if (helpBtn && voiceIntro) {
      helpBtn.onclick = function () { voiceIntro.classList.add('show'); };
      var voiceIntroClose = document.getElementById('cp-voice-intro-close');
      if (voiceIntroClose) voiceIntroClose.onclick = function () { voiceIntro.classList.remove('show'); };
      voiceIntro.onclick = function (e) { if (e.target === voiceIntro) voiceIntro.classList.remove('show'); };
    }

    // 上下文/首次缓存状态（与 DeepSeek Harness 的上下文准备提示对齐）
    function setContextStatus(text, tone, count) {
      var box = el('cp-context');
      if (!box) return;
      var ring = el('cp-context-ring');
      var textEl = el('cp-context-text');
      if (ring) {
        if (count) {
          var max = 100;
          var pct = Math.max(0, Math.min(100, (count / max) * 100));
          var deg = Math.round(pct * 3.6);
          ring.style.background = 'conic-gradient(var(--brand) ' + deg + 'deg,var(--n-200) ' + deg + 'deg)';
          ring.title = '上下文：' + count + ' 条';
        } else {
          ring.style.background = 'conic-gradient(var(--n-200) 0deg,var(--n-200) 360deg)';
          ring.title = '上下文：0 条';
        }
      }
      if (textEl) {
        textEl.textContent = text;
        textEl.style.color = tone === 'ready' ? 'var(--green-700,#047857)' : tone === 'error' ? '#dc2626' : 'var(--n-500,#64748b)';
      }
    }
    window.composerContextStatus = setContextStatus;
    document.addEventListener('lab:context-preparing', function () {
      setContextStatus('上下文：首次缓存准备中…', '');
    });
    document.addEventListener('lab:context-ready', function (event) {
      var d = (event && event.detail) || {};
      var count = d.turns || d.messages || 0;
      setContextStatus(count ? ('上下文：已就绪（' + count + ' 条）') : '上下文：已就绪（首次会话）', 'ready', count);
    });
    setContextStatus('上下文：等待加载…', '', 0);

    // 模型：弹出供应商/模型选择器，点击即切换当前模型
    var cpModel = el('cp-model');
    var cpModelPop = el('cp-model-pop');
    function closeModelPop() {
      if (cpModelPop) cpModelPop.classList.remove('on');
    }
    function openModelPop() {
      if (!cpModelPop) return;
      cpModelPop.classList.add('on');
      var list = el('cp-model-list');
      if (list) list.innerHTML = '<div style="padding:14px;color:#94a3b8;font-size:12px">正在加载模型…</div>';
      fetch('/settings/providers').then(function (r) { return r.json(); }).then(function (data) {
        var items = (data.items || []).filter(function (x) { return x.model; });
        if (!list) return;
        var activeItem = items.filter(function (x) { return x.active; })[0];
        var thinkingRow = el('cp-thinking-row');
        var thinkingSelect = el('cp-thinking-level');
        if (thinkingRow && thinkingSelect) {
          if (activeItem && activeItem.supports_thinking) {
            thinkingRow.style.display = 'flex';
            thinkingSelect.value = (data.settings && data.settings.thinking_level) || 'auto';
          } else {
            thinkingRow.style.display = 'none';
          }
          thinkingSelect.onchange = function () {
            fetch('/settings', {
              method: 'PUT',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({thinking_level: thinkingSelect.value})
            }).then(function () { refresh(); });
          };
        }
        list.innerHTML = items.map(function (x) {
          var active = x.active;
          return '<div class="cp-model-row' + (active ? ' active' : '') + '" data-provider="' + x.id + '">'
            + '<span class="m-label">' + esc(x.label) + ' · ' + esc(x.model) + '</span>'
            + (active ? '<span class="m-check">✓</span>' : '<span class="m-meta">' + x.kind + '</span>')
            + '</div>';
        }).join('') || '<div style="padding:14px;color:#94a3b8;font-size:12px">还没有可用供应商</div>';
        Array.prototype.forEach.call(list.querySelectorAll('.cp-model-row'), function (row) {
          row.onclick = function () {
            var id = row.dataset.provider;
            var item = items.filter(function (x) { return x.id === id; })[0];
            if (!item) return;
            fetch('/settings', {
              method: 'PUT',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                provider_id: id,
                provider_label: item.label,
                base_url: item.base_url,
                model_name: item.model
              })
            }).then(function (r) { return r.json(); }).then(function () {
              closeModelPop();
              if (window.logAction) window.logAction('composer_switch_model', { provider: id, model: item.model });
              refresh();
            });
          };
        });
      }).catch(function () {
        if (list) list.innerHTML = '<div style="padding:14px;color:#c2410c;font-size:12px">读取供应商失败</div>';
      });
    }
    if (cpModel) {
      cpModel.onclick = function (e) {
        e.stopPropagation();
        openModelPop();
      };
      var modelCustom = el('cp-model-custom');
      if (modelCustom) modelCustom.onclick = function (e) {
        e.stopPropagation();
        closeModelPop();
        if (window.shellShow) window.shellShow('settings');
      };
      var modelClose = el('cp-model-close');
      if (modelClose) modelClose.onclick = closeModelPop;
      document.addEventListener('click', function (e) {
        if (!e.target.closest('#cp-model') && !e.target.closest('#cp-model-pop')) closeModelPop();
      });
    }
    var cpMode = el('cp-mode');
    var cpModePop = el('cp-mode-pop');
    var MODE_LABELS = { protocol: '方案实验', template: 'AI制作方案/配方', storage: '制作储存库' };
    function modeNameFromSession(d) {
      if (d.mode === 'protocol' && d.protocol) return '方案实验';
      if (d.mode === 'template') return 'AI制作方案/配方';
      if (d.mode === 'storage') return '制作储存库';
      return '方案实验';
    }
    function setModeLabel(label) {
      if (cpMode) el('cp-mode-name').textContent = label;
    }
    function closeModePop() {
      if (cpModePop) cpModePop.classList.remove('on');
    }
    function openModePop() {
      if (!cpModePop) return;
      var active = cpModePop.classList.toggle('on');
      if (active) {
        Array.prototype.forEach.call(cpModePop.querySelectorAll('.cp-mode-pop-row'), function (row) {
          row.classList.toggle('active', el('cp-mode-name').textContent === row.querySelector('span').textContent);
        });
      }
    }
    if (cpMode) {
      cpMode.onclick = function (e) {
        e.stopPropagation();
        openModePop();
      };
      Array.prototype.forEach.call(cpModePop.querySelectorAll('.cp-mode-pop-row'), function (row) {
        row.onclick = function (e) {
          e.stopPropagation();
          closeModePop();
          var mode = row.dataset.mode;
          if (window.logAction) window.logAction('composer_mode', { mode: mode });
          selectComposerMode(mode).then(function (ok) {
            if (ok && mode === 'protocol') setModeLabel('方案实验');
            else if (ok && mode === 'template') setModeLabel('AI制作方案/配方');
            else if (ok && mode === 'storage') setModeLabel('制作储存库');
            else setModeLabel('方案实验');
          });
        };
      });
      document.addEventListener('click', function (e) {
        if (!e.target.closest('#cp-mode') && !e.target.closest('#cp-mode-pop')) closeModePop();
      });
    }
    // 开发指标（轮数/工具调用/耗时/字数）默认不给实验员看；
    // 需要时在控制台 localStorage.setItem('lab-dev-metrics','1') 后刷新。
    if (localStorage.getItem('lab-dev-metrics') === '1') {
      document.body.classList.add('lab-dev-metrics');
    }
    renderMeta();
    refresh();
    setInterval(refresh, 6000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(init, 60); });
  } else {
    setTimeout(init, 60);
  }
})();
