// 工作画布：实验进行中的可视化主区。
// 参考 deepseek-harness：
//   - 工具调用用 presentCall/presentResult 卡片，调用前先出待执行卡
//   - 步骤时间线在顶部，当前步高亮
(function () {
  var CSS = [
    '#rc{max-width:860px;margin:0 auto}',
    // 步骤时间线：紧凑一行，不再是大方块
    '#rc-steps{display:flex;gap:4px;overflow-x:auto;padding:0 0 12px;align-items:center}',
    '.rc-step{flex:0 0 auto;display:flex;align-items:center;gap:6px;background:var(--n-00);border:1px solid var(--bd-2);border-radius:999px;padding:4px 11px 4px 5px;cursor:pointer;font-size:var(--fs-sm);color:var(--n-700);white-space:nowrap}',
    '.rc-step:hover{border-color:var(--bd-3)}',
    '.rc-step.cur{border-color:var(--brand);color:var(--brand-strong);background:var(--brand-50)}',
    '.rc-step.done{color:var(--n-500)}',
    '.rc-sn{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;background:var(--n-200);color:var(--n-700);font-size:10px;font-weight:600;flex:0 0 17px}',
    '.rc-step.cur .rc-sn{background:var(--brand);color:#fff}',
    '.rc-step.done .rc-sn{background:var(--green-500);color:#fff}',
    '.rc-step.pending .rc-sn{background:#d97706;color:#fff}',
      '.rc-progress{height:6px;background:var(--n-100);border-radius:999px;overflow:hidden;margin:0 0 6px}',
      '.rc-progress-bar{height:100%;background:var(--brand);border-radius:999px;transition:width .25s ease}',
      '.rc-progress-text{font-size:var(--fs-xs);color:var(--n-500);margin-bottom:12px}',
    // 卡片：一个大步骤 + 其小步骤
    '.rc-card{background:var(--n-00);border:1px solid var(--bd-2);border-radius:var(--r-lg);margin-bottom:10px;overflow:hidden}',
    '.rc-card-h{padding:12px 15px;display:flex;align-items:flex-start;gap:10px;border-bottom:1px solid var(--bd-1)}',
    '.rc-card-h.plain{border-bottom:0}',
    '.rc-badge{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:var(--r-sm);background:var(--brand-50);color:var(--brand-strong);font-size:var(--fs-xs);font-weight:600;margin-top:1px}',
    '.rc-hmain{flex:1;min-width:0}',
    '.rc-t{font-size:var(--fs-lg);font-weight:600;color:var(--n-900);line-height:1.4}',
    '.rc-sub{font-size:var(--fs-sm);color:var(--n-600);margin-top:3px;line-height:1.6}',
    '.rc-body{padding:12px 15px}',
    // 小步骤列表
    '.rc-sub-item{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--bd-1)}',
    '.rc-sub-item:last-child{border-bottom:0}',
    '.rc-sub-n{flex:0 0 18px;height:18px;border-radius:50%;border:1px solid var(--bd-3);color:var(--n-600);font-size:10px;display:inline-flex;align-items:center;justify-content:center;margin-top:1px}',
    '.rc-sub-c{flex:1;min-width:0}',
    '.rc-sub-t{font-size:var(--fs-md);color:var(--n-900);line-height:1.6}',
    '.rc-kv{display:inline-block;background:var(--n-75);color:var(--n-700);border-radius:var(--r-sm);padding:2px 7px;margin:4px 5px 0 0;font-size:var(--fs-xs)}',
    '.rc-kv.rec{background:var(--amber-100);color:var(--amber-600)}',
    '.rc-lbl{font-size:var(--fs-xs);color:var(--n-500);margin:12px 0 4px}',
    '.rc-lbl:first-child{margin-top:0}',
    // 安全条
    '.rc-safe{border:1px solid var(--bd-2);border-left:2px solid var(--red-500);background:var(--red-50);border-radius:var(--r-md);padding:10px 13px;margin-bottom:10px}',
    '.rc-safe.mild{border-left-color:var(--green-500);background:var(--green-100)}',
    '.rc-safe b{color:var(--red-600);display:block;margin-bottom:3px;font-size:var(--fs-md);font-weight:600}',
    '.rc-safe.mild b{color:var(--green-900)}',
    '.rc-safe div{color:var(--n-800);font-size:var(--fs-sm);line-height:1.65}',
    '.rc-safe small{color:var(--n-500);font-size:var(--fs-xs);display:block;margin-top:5px}',
    // 思维链
    '.rc-think{margin-bottom:1px;overflow:hidden}','.rc-think-row .dot,.rc-tool-h .dot{color:rgba(0,0,0,.2);flex:0 0 auto}',
    '.rc-think-row{display:flex;align-items:center;gap:7px;padding:5px 2px;cursor:pointer;position:relative;overflow:hidden}',
    '.rc-think-row .ic{font-size:11px;color:var(--n-500);flex:0 0 auto}',
    '.rc-think-row .tt{font-size:var(--fs-sm);font-weight:500;color:var(--n-800);flex:0 0 auto}',
    '.rc-think-row .sep{width:1px;height:11px;background:var(--bd-2);flex:0 0 auto}',
    '.rc-think-row .sm{font-size:var(--fs-sm);color:var(--n-600);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}',
    '.rc-think-row .cv{color:var(--n-400);font-size:var(--fs-xs);flex:0 0 auto}',
    '.rc-think.running .rc-think-row::after{content:"";position:absolute;inset-block:0;left:-260px;width:260px;background:linear-gradient(90deg,transparent,rgba(0,0,0,.035),transparent);animation:rcsweep 2.6s ease-out infinite;pointer-events:none}',
    '@keyframes rcsweep{0%{left:-260px}90%,100%{left:100%}}',
    '.rc-think-body{margin:2px 0 8px 22px;padding:9px 12px;background:var(--n-60);border-radius:var(--r-md);color:var(--n-700);font-size:var(--fs-sm);line-height:1.75;white-space:pre-wrap;display:none}',
    '.rc-think.open .rc-think-body{display:block}',
    // 工具卡片
    '.rc-tool{margin-bottom:1px}','.rc-name{font-weight:500;color:var(--n-800);flex:0 0 auto}','.rc-sum{color:var(--n-600);font-size:var(--fs-sm);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}',

    '.rc-tool.error .rc-name{color:var(--red-600)}',
    '.rc-tool-h{display:flex;align-items:center;gap:7px;font-size:var(--fs-md);padding:5px 2px;min-width:0}',
    '.rc-ic{width:15px;text-align:center;font-size:12px;color:var(--n-500);flex:0 0 15px}',
    '.rc-ic.read{background:var(--brand-50);color:var(--brand-strong)}',
    '.rc-ic.execute{background:var(--brand-100);color:var(--brand-strong)}',
    '.rc-state{margin-left:auto;font-size:var(--fs-xs);font-weight:400;color:var(--n-500)}',
    '.rc-tool-b{margin:2px 0 8px 22px;padding:9px 12px;background:var(--n-60);border-radius:var(--r-md);color:var(--n-700);font-size:var(--fs-sm);line-height:1.7}',
    '.rc-tool-b .warn{color:var(--red-600)}',
    '.rc-spin{display:inline-block;width:9px;height:9px;border:1.5px solid var(--brand-100);border-top-color:var(--brand);border-radius:50%;animation:rcspin .7s linear infinite}',
    '@keyframes rcspin{to{transform:rotate(360deg)}}',
    '.rc-sec-title{font-size:var(--fs-xs);color:var(--n-500);margin:16px 0 7px;display:flex;align-items:center;gap:8px}',
    '.rc-sec-title::after{content:"";flex:1;height:1px;background:var(--bd-1)}'
  ].join('');

  var session = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }
  function api(path, method, payload) {
    var options = { method: method || 'GET' };
    if (payload) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (r) { return r.json(); });
  }
  function stepsHtml() {
    if (!session || session.mode !== 'protocol' || !session.all_steps) return '';
    var cur = session.step.number;
    return '<div id="rc-steps">' + session.all_steps.map(function (s) {
      var status = (session.step_statuses || {})[String(s.number)];
      var cls = s.number === cur ? ' cur'
        : (status === 'completed' ? ' done'
        : (status === 'left_with_pending' ? ' pending' : ''));
      return '<div class="rc-step' + cls + '" data-n="' + s.number + '">'
        + '<span class="rc-sn">' + s.number + '</span>'
        + esc(s.title)
        + (status === 'left_with_pending' ? '<span style="color:#b45309;font-size:var(--fs-xs)">·有暂缓问题</span>' : '')
        + (s.substep_count ? '<span style="color:var(--n-400);font-size:var(--fs-xs)">·' + s.substep_count + '</span>' : '') + '</div>';
    }).join('') + '</div>';
  }

  function stepCardHtml() {
    if (!session) return '';
    if (session.mode !== 'protocol') {
      return '<div class="rc-card"><div class="rc-t">自由记录模式</div>'
        + '<p class="rc-p">未选择实验方案，系统只做记录，不产生方案性追问与安全提示。'
        + '到左侧「实验方案」可选择一份。</p></div>';
    }
    var s = session.step;
    var planned = Object.keys(s.protocol_values).map(function (k) {
      return '<span class="rc-kv">' + esc(k) + ' = ' + esc(s.protocol_values[k]) + '</span>';
    }).join('') || '<span style="color:#94a3b8;font-size:12px">无</span>';
    var must = s.must_record.map(function (k) {
      return '<span class="rc-kv rec">' + esc(k) + '</span>';
    }).join('') || '<span style="color:#94a3b8;font-size:12px">无</span>';
    var safety = (session.safety || []).map(function (r) {
      var danger = r.critical;
      return '<div class="rc-safe' + (danger ? '' : ' mild') + '">'
        + '<b>' + (danger ? '高危试剂：' : '涉及试剂：') + esc(r.name)
        + (r.cas ? '（CAS ' + esc(r.cas) + '）' : '') + '</b>'
        + (danger ? r.statements.map(function (t) { return '<div>· ' + esc(t) + '</div>'; }).join('')
                  : '<div>无高危项</div>')
        + '<small>' + (danger && r.codes.length ? 'GHS ' + r.codes.join('/') + '　' : '')
        + esc(session.safety_note || '') + '</small></div>';
    }).join('');
    // 一个大步骤 + 它的小步 = 一张卡片
    var subs = (s.substeps || []).map(function (x) {
      return '<div class="rc-sub-item"><div class="rc-sub-n">' + x.order + '</div>'
        + '<div class="rc-sub-c"><div class="rc-sub-t">' + esc(x.text) + '</div>'
        + (x.note ? '<div style="color:var(--amber-600);font-size:var(--fs-xs);margin-top:3px">' + esc(x.note) + '</div>' : '')
        + '</div></div>';
    }).join('');
    var pct = Math.round((s.number / session.protocol.total_steps) * 100);
      var progress = '<div class="rc-progress"><div class="rc-progress-bar" style="width:' + pct + '%"></div></div>'
        + '<div class="rc-progress-text">步骤 ' + s.number + ' / ' + session.protocol.total_steps + ' · 完成 ' + pct + '%</div>';
      return progress + safety
      + (s.hazard_note ? '<div class="rc-safe mild"><b>方案自带提示</b><div>' + esc(s.hazard_note) + '</div></div>' : '')
      + '<div class="rc-card">'
      + '<div class="rc-card-h' + (subs ? '' : ' plain') + '">'
      + '<span class="rc-badge">' + s.number + '</span>'
      + '<div class="rc-hmain"><div class="rc-t">' + esc(s.title) + '</div>'
      + '<div class="rc-sub">' + esc(s.instruction) + '</div></div>'
      + '<button class="sh-btn" id="rc-edit" style="flex:0 0 auto">编辑</button></div>'
      + (subs ? '<div class="rc-body" style="padding-bottom:4px">' + subs + '</div>' : '')
      + '<div class="rc-body" style="border-top:1px solid var(--bd-1)">'
      + '<div class="rc-lbl">方案已定（不会追问）</div><div>' + planned + '</div>'
      + '<div class="rc-lbl">现场必测（缺了会追问）</div><div>' + must + '</div>'
      + '<div style="display:flex;gap:7px;margin-top:13px">'
      + '<button class="sh-btn" id="rc-prev">上一步</button>'
      + '<button class="sh-btn primary" id="rc-next">下一步</button></div></div></div>';
  }

  function paint() {
    var canvas = window.shellCanvas && window.shellCanvas();
    if (!canvas || window.shellCurrentView() !== 'run') return;
    if (!session) {
      canvas.classList.add('empty');
      canvas.innerHTML = '加载中…';
      return;
    }
    canvas.classList.remove('empty');
    canvas.innerHTML = '<div id="rc">' + stepsHtml() + stepCardHtml() + '</div>';

    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-step'), function (node) {
      node.onclick = function () {
        window.moveProtocolStep('jump', parseInt(node.dataset.n, 10))
          .then(reload).catch(function (error) { window.alert(error.message); });
      };
    });
    var edit = document.getElementById('rc-edit');
    if (edit) edit.onclick = function () { if (window.openProtocolEditor) window.openProtocolEditor(); };
    var prev = document.getElementById('rc-prev'), next = document.getElementById('rc-next');
    if (prev) prev.onclick = function () { window.moveProtocolStep('prev').then(reload).catch(function (error) { window.alert(error.message); }); };
    if (next) next.onclick = function () { window.moveProtocolStep('next').then(reload).catch(function (error) { window.alert(error.message); }); };
  }

  function reload() {
    var path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session/steps')
      : '/protocols/session/steps';
    return api(path).then(function (d) { session = d; paint(); return d; })
      .catch(function () {});
  }

  window.runCanvasRender = function () { paint(); reload(); };
  window.runReload = reload;

  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);
  document.addEventListener('shell-ready', function () {
    reload();
    setInterval(function () { if (window.shellCurrentView() === 'run') reload(); }, 6000);
  });
})();
