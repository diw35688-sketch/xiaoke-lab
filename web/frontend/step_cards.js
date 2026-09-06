// 状态机卡片栏：把实验方案的每一步做成可左右滑动的卡片，当前步高亮，点卡片可跳转。
(function () {
  var CSS = [
    '#steps-rail{flex:0 0 auto;background:transparent;border-top:1px solid rgba(226,232,240,.7);padding:4px 16px 2px;display:none}',
    '#steps-rail.on{display:block}',
    '#steps-inner{position:relative;display:flex;gap:14px;overflow-x:auto;padding:14px 18px 18px;scroll-behavior:smooth;pointer-events:auto;scrollbar-width:thin;scrollbar-color:#cbd5e1 transparent}',
    '#steps-inner::-webkit-scrollbar{height:6px}',
    '#steps-inner::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:99px}',
    '.step-card{flex:0 0 330px;background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:18px 20px;min-height:128px;box-shadow:0 6px 20px rgba(15,23,42,.08);cursor:pointer;transition:opacity .2s,transform .2s,box-shadow .2s;box-sizing:border-box;opacity:.72;transform:scale(.94)}',
    '.step-card:hover{opacity:.95;transform:scale(.98);box-shadow:0 10px 28px rgba(15,23,42,.12)}',
    '.step-card.current{opacity:1;transform:scale(1.04);border-color:#2563eb;box-shadow:0 0 0 2px #bfdbfe,0 12px 30px rgba(37,99,235,.16);z-index:2}',
    '.step-card.done{opacity:.5;filter:saturate(.6)}',
    '.step-card.pending{opacity:.8}',
    '.sc-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}',
    '.sc-icon{width:32px;height:32px;border-radius:10px;background:#eef2ff;color:#2563eb;display:flex;align-items:center;justify-content:center;flex:0 0 32px}',
    '.sc-icon svg{display:block}',
    '.sc-num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#94a3b8;color:#fff;font-size:12px;font-weight:700}',
    '.step-card.done .sc-num{background:#16a34a}',
    '.step-card.pending .sc-num{background:#d97706}',
    '.step-card.current .sc-num{background:#2563eb}',
    '.sc-title{font-weight:600;color:#0f172a;font-size:15px;margin-bottom:6px;line-height:1.5}',
    '.sc-text{color:#64748b;font-size:13px;line-height:1.6;max-height:54px;overflow:hidden}',
    '.sc-badges{margin-top:10px;display:flex;flex-wrap:wrap;gap:4px}',
    '.sc-b{font-size:10px;border-radius:6px;padding:3px 7px;background:#e0e7ff;color:#3730a3}',
    '.sc-b.rec{background:#fef3c7;color:#92400e}',
    '.sc-b.danger{background:#fee2e2;color:#b91c1c}',
    '#steps-head{display:flex;align-items:center;gap:10px;pointer-events:auto;font-size:12px;color:#475569;padding-left:4px;text-shadow:0 1px 2px #fff}',
    '#steps-head b{color:#0f172a;font-size:13px}'
  ].join('');

  var data = null;
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }

  function render() {
    var rail = el('steps-rail'), inner = el('steps-inner');
    if (!data || data.mode !== 'protocol' || !data.all_steps || !data.all_steps.length) {
      rail.classList.remove('on');
      return;
    }
    rail.classList.add('on');
    var cur = data.step.number;
    el('steps-head').innerHTML = '<b>' + esc(data.protocol.title) + '</b>'
      + '<span>第 ' + cur + ' / ' + data.protocol.total_steps + ' 步 · 点卡片可跳转</span>';
    inner.innerHTML = data.all_steps.map(function (s) {
      var status = (data.step_statuses || {})[String(s.number)];
      var extra = s.number === cur ? ' current'
        : (status === 'completed' ? ' done'
        : (status === 'left_with_pending' ? ' pending' : ''));
      var badges = '';
      var planned = Object.keys(s.protocol_values || {}).length;
      if (planned) badges += '<span class="sc-b">方案已定 ' + planned + ' 项</span>';
      (s.must_record || []).forEach(function (f) {
        badges += '<span class="sc-b rec">必测 ' + esc(f) + '</span>';
      });
      if (s.has_hazard) badges += '<span class="sc-b danger">安全提示</span>';
      if (status === 'left_with_pending') badges += '<span class="sc-b rec">有暂缓问题</span>';
      return '<div class="step-card' + extra + '" data-n="' + s.number + '" title="'
        + esc(s.instruction || s.title) + '">'
        + '<div class="sc-head"><div class="sc-icon">'
        + '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 2v6.3L4.6 17.8A2 2 0 0 0 6.4 21h11.2a2 2 0 0 0 1.8-3.2L14 8.3V2"/><path d="M8.5 2h7"/><path d="M7.2 15h9.6"/></svg>'
        + '</div><span class="sc-num">' + s.number + '</span></div>'
        + '<div class="sc-title">' + esc(s.title) + '</div>'
        + '<div class="sc-text">' + esc(s.instruction) + '</div>'
        + '<div class="sc-badges">' + badges + '</div></div>';
    }).join('');
    Array.prototype.forEach.call(inner.querySelectorAll('.step-card'), function (card) {
      card.onclick = function () {
        window.moveProtocolStep('jump', parseInt(card.dataset.n, 10))
          .then(function () { load(); if (window.chatHomeReload) window.chatHomeReload(); })
          .catch(function (error) { window.alert(error.message); });
      };
    });
    var active = inner.querySelector('.step-card.current');
    if (active) inner.scrollLeft = Math.max(0, active.offsetLeft - (inner.clientWidth - active.offsetWidth) / 2);
  }

  function load() {
    var path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session/steps')
      : '/protocols/session/steps';
    return fetch(path).then(function (r) { return r.json(); })
      .then(function (d) { data = d; render(); return d; })
      .catch(function () {});
  }
  window.labStepsReload = load;

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
    var rail = document.createElement('div');
    rail.id = 'steps-rail';
    rail.innerHTML = '<div id="steps-head"></div><div id="steps-inner"></div>';
    // 步骤卡属于「实验内容」，归中栏那页纸；此前挂在右侧聊天栏顶部（sh-chat-head 之后），
    // 视觉上跑到右上角，与"记录本"的心智不符（2026-08-30 用户指出）。
    // 挂到中栏、纸的正上方（#sh-top 与 #sh-canvas 之间）。
    // 不放进 #sh-canvas 内部：切换视图时 show() 会整块重写画布 innerHTML，会把卡片冲掉。
    var canvas = document.getElementById('sh-canvas');
    var center = document.getElementById('sh-center');
    if (center && canvas) {
      center.insertBefore(rail, canvas);
    } else if (center) {
      center.appendChild(rail);
    } else {
      document.body.appendChild(rail);
    }
    load();
    setInterval(load, 4000);
  }

  function ensureInit() {
    if (document.getElementById('sh-chat')) {
      init();
      return;
    }
    document.addEventListener('shell-ready', ensureInit, {once: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureInit);
  } else {
    ensureInit();
  }
})();
