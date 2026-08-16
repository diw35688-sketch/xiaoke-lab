// 对话输入区（composer）：对齐 deepseek-harness 的 InputBar 规格。
//   卡片圆角 22px，边框 rgba(0,0,0,.10)，textarea 16px/24px，
//   textarea 与控制行间距 12px，卡片顶部内边距 10px，控制行 padding 2px 8px 6px。
// 结构上是「一张卡片包住输入框 + 控制行」，而不是输入框和按钮各自为政。
(function () {
  var CSS = [
    '#cp-wrap{padding:0 16px 10px;background:var(--n-00);flex:0 0 auto}',
    '#cp-card{box-sizing:border-box;position:relative;display:flex;flex-direction:column;gap:12px;',
    '  width:100%;padding-top:10px;border:1px solid rgba(0,0,0,.10);border-radius:22px;',
    '  background:var(--n-00);box-shadow:0 1px 2px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.05)}',
    '#cp-card.focus{border-color:rgba(0,0,0,.16)}',
    '#cp-text{border:0;outline:0;resize:none;width:100%;box-sizing:border-box;padding:0 16px;',
    '  font-size:15px;line-height:23px;font-family:inherit;color:var(--n-900);background:transparent;',
    '  max-height:168px;overflow-y:auto}',
    '#cp-text::placeholder{color:var(--n-400)}',
    '#cp-row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:2px 8px 6px;min-width:0}',
    '.cp-left,.cp-right{display:flex;align-items:center;gap:7px;min-width:0}',
    '.cp-icon{width:30px;height:30px;border-radius:50%;border:1px solid rgba(0,0,0,.10);background:var(--n-00);',
    '  color:var(--n-600);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:15px;flex:0 0 auto;font-family:inherit}',
    '.cp-icon:hover{background:var(--n-60)}',
    '.cp-icon.rec{background:var(--red-500);border-color:var(--red-500);color:#fff}',
    '.cp-chip{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 10px;border-radius:15px;',
    '  border:1px solid rgba(0,0,0,.10);background:var(--n-00);color:var(--n-700);font-size:var(--fs-sm);',
    '  cursor:pointer;white-space:nowrap;font-family:inherit;max-width:190px;overflow:hidden;text-overflow:ellipsis}',
    '.cp-chip:hover{background:var(--n-60)}',
    '.cp-chip .v{color:var(--n-500)}',
    '.cp-chip.plain{border:0;background:transparent;padding:0 4px;cursor:default}',
    '#cp-send{width:32px;height:32px;border-radius:50%;border:0;background:var(--brand);color:#fff;',
    '  cursor:pointer;display:inline-flex;align-items:center;justify-content:center;font-size:15px;flex:0 0 auto}',
    '#cp-send:hover{background:var(--brand-strong)}',
    '#cp-send:disabled{background:var(--n-200);color:var(--n-500);cursor:not-allowed}',
    '#cp-meta{padding:6px 16px 0;font-size:var(--fs-xs);color:var(--n-500);display:flex;gap:8px;flex-wrap:wrap;line-height:1.6}',
    '#cp-meta .sep{color:var(--n-200)}',
    // 下拉面板
    '#cp-pop{position:absolute;bottom:44px;right:8px;background:var(--n-00);border:1px solid rgba(0,0,0,.10);',
    '  border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.12);min-width:250px;padding:5px;display:none;z-index:30}',
    '#cp-pop.on{display:block}',
    '.cp-pop-row{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:8px;font-size:var(--fs-md);color:var(--n-800);cursor:pointer}',
    '.cp-pop-row:hover{background:var(--n-60)}',
    '.cp-pop-row .k{flex:0 0 auto}',
    '.cp-pop-row .v{margin-left:auto;color:var(--n-500);display:flex;align-items:center;gap:4px}',
    '.cp-pop-row .chev{color:var(--n-400);font-size:11px}'
  ].join('');

  var HTML = [
    '<div id="cp-card">',
    '  <textarea id="cp-text" rows="1" placeholder="给实验助手发消息，或按住麦克风口述"></textarea>',
    '  <div id="cp-row">',
    '    <div class="cp-left">',
    '      <button class="cp-icon" id="cp-mic" title="语音输入">◉</button>',
    '      <span class="cp-chip plain" id="cp-hint">本地识别 SenseVoice</span>',
    '    </div>',
    '    <div class="cp-right">',
    '      <button class="cp-chip" id="cp-model"><span id="cp-model-name">未配置模型</span><span class="v">⌄</span></button>',
    '      <button id="cp-send" title="发送">↑</button>',
    '    </div>',
    '  </div>',
    '  <div id="cp-pop">',
    '    <div class="cp-pop-row" data-go="settings"><span class="k">模型</span><span class="v" id="cp-pop-model">—<span class="chev">›</span></span></div>',
    '    <div class="cp-pop-row" data-go="settings"><span class="k">语音合成</span><span class="v" id="cp-pop-tts">—<span class="chev">›</span></span></div>',
    '    <div class="cp-pop-row" data-go="protocols"><span class="k">实验方案</span><span class="v" id="cp-pop-proto">—<span class="chev">›</span></span></div>',
    '  </div>',
    '</div>',
    '<div id="cp-meta"></div>'
  ].join('');

  function el(id) { return document.getElementById(id); }

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

  function autoGrow() {
    var box = el('cp-text');
    box.style.height = 'auto';
    box.style.height = Math.min(168, box.scrollHeight) + 'px';
  }

  function send() {
    var box = el('cp-text');
    var text = box.value.trim();
    if (!text) return;
    var input = document.querySelector('#message');
    var form = document.querySelector('#form');
    if (!input || !form) return;
    input.value = text;
    box.value = '';
    autoGrow();
    stats.turns += 1;
    renderMeta();
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
  window.composerSend = function (text) {
    el('cp-text').value = text;
    send();
  };

  function refresh() {
    fetch('/settings').then(function (r) { return r.json(); }).then(function (d) {
      var name = d.ready ? d.settings.model_name : '未配置模型';
      el('cp-model-name').textContent = name;
      el('cp-pop-model').innerHTML = (d.settings.model_name || '—') + '<span class="chev">›</span>';
      el('cp-send').disabled = !d.ready;
    }).catch(function () {});
    fetch('/tts/providers').then(function (r) { return r.json(); }).then(function (d) {
      var meta = (d.providers || []).filter(function (p) { return p.id === d.current.provider; })[0];
      el('cp-pop-tts').innerHTML = (meta ? meta.label.split('（')[0] : '—') + '<span class="chev">›</span>';
    }).catch(function () {});
    fetch('/protocols/session').then(function (r) { return r.json(); }).then(function (d) {
      el('cp-pop-proto').innerHTML = (d.mode === 'protocol'
        ? d.protocol.title + ' 第' + d.step.number + '步' : '自由记录') + '<span class="chev">›</span>';
    }).catch(function () {});
  }
  window.composerRefresh = refresh;

  function init() {
    var host = document.getElementById('sh-chat');
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
    box.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    });
    el('cp-send').onclick = send;

    // 麦克风：复用已有的录音实现
    el('cp-mic').onclick = function () {
        if (window.phoneCallToggle) { window.phoneCallToggle(); return; }
      var real = document.getElementById('asr-btn');
      if (!real) return;
      real.click();
      var on = el('cp-mic').classList.toggle('rec');
      el('cp-mic').textContent = on ? '■' : '◉';
      el('cp-hint').textContent = on ? '正在录音，再点一次结束' : '本地识别 SenseVoice';
    };

    // 模型/语音/方案 快捷面板
    el('cp-model').onclick = function (e) {
      e.stopPropagation();
      el('cp-pop').classList.toggle('on');
      refresh();
    };
    document.addEventListener('click', function () { el('cp-pop').classList.remove('on'); });
    el('cp-pop').onclick = function (e) { e.stopPropagation(); };
    Array.prototype.forEach.call(el('cp-pop').querySelectorAll('.cp-pop-row'), function (row) {
      row.onclick = function () {
        el('cp-pop').classList.remove('on');
        if (window.shellShow) window.shellShow(row.dataset.go);
      };
    });

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
