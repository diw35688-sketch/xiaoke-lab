// 状态机卡片栏：把实验方案的每一步做成可左右滑动的卡片，当前步高亮，点卡片可跳转。
(function () {
  var CSS = [
    '#steps-rail{flex:0 0 auto;background:#fff;border-top:1px solid #e2e8f0;padding:0 16px;display:none}',
    '#steps-rail.on{display:block}',
    '#steps-inner{display:flex;gap:12px;overflow-x:auto;padding:10px 4px 14px;scroll-behavior:smooth;pointer-events:auto}',
    '#steps-inner::-webkit-scrollbar{height:6px}',
    '#steps-inner::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:99px}',
    '.step-card{flex:0 0 230px;background:#fff;border:1px solid #e2e8f0;border-radius:13px;padding:12px 14px;box-shadow:0 3px 14px rgba(15,23,42,.09);cursor:pointer;transition:.16s;box-sizing:border-box}',
    '.step-card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(15,23,42,.14)}',
    '.step-card.current{border-color:#2563eb;box-shadow:0 0 0 2px #bfdbfe,0 6px 20px rgba(37,99,235,.18)}',
    '.step-card.done{opacity:.62}',
    '.step-card.done .sc-num{background:#16a34a}',
    '.step-card.current .sc-num{background:#2563eb}',
    '.sc-num{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:#94a3b8;color:#fff;font-size:12px;font-weight:700;margin-bottom:7px}',
    '.sc-title{font-weight:600;color:#0f172a;font-size:13px;margin-bottom:5px}',
    '.sc-text{color:#64748b;font-size:12px;line-height:1.5;max-height:52px;overflow:hidden}',
    '.sc-badges{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px}',
    '.sc-b{font-size:10px;border-radius:5px;padding:2px 6px;background:#e0e7ff;color:#3730a3}',
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
      var extra = s.number === cur ? ' current' : (s.number < cur ? ' done' : '');
      var badges = '';
      var planned = Object.keys(s.protocol_values || {}).length;
      if (planned) badges += '<span class="sc-b">方案已定 ' + planned + ' 项</span>';
      (s.must_record || []).forEach(function (f) {
        badges += '<span class="sc-b rec">必测 ' + esc(f) + '</span>';
      });
      if (s.has_hazard) badges += '<span class="sc-b danger">安全提示</span>';
      return '<div class="step-card' + extra + '" data-n="' + s.number + '">'
        + '<div class="sc-num">' + s.number + '</div>'
        + '<div class="sc-title">' + esc(s.title) + '</div>'
        + '<div class="sc-text">' + esc(s.instruction) + '</div>'
        + '<div class="sc-badges">' + badges + '</div></div>';
    }).join('');
    Array.prototype.forEach.call(inner.querySelectorAll('.step-card'), function (card) {
      card.onclick = function () {
        fetch('/protocols/session/move', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'jump', step_number: parseInt(card.dataset.n, 10) })
        }).then(function () { load(); });
      };
    });
    var active = inner.querySelector('.step-card.current');
    if (active) inner.scrollLeft = Math.max(0, active.offsetLeft - 90);
  }

  function load() {
    return fetch('/protocols/session/steps').then(function (r) { return r.json(); })
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
    (document.getElementById('sh-center') || document.body).appendChild(rail);
    load();
    setInterval(load, 4000);
  }

  // 步骤时间线已并入中间工作画布顶部，不再单独渲染。
  void init;
})();
