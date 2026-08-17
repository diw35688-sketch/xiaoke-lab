// 方案编辑器：改大步骤标题、说明、小步、方案已定值、现场必测字段与追问话术。
// 保存前由后端契约校验，校验不过整笔拒绝，不会写出半成品。
(function () {
  var CSS = [
    '#pe-mask{position:fixed;inset:0;background:rgba(0,0,0,.24);display:none;align-items:center;justify-content:center;z-index:9999}',
    '#pe-mask.on{display:flex}',
    '#pe{background:var(--n-00);border-radius:var(--r-lg);width:min(660px,94vw);max-height:88vh;display:flex;flex-direction:column;box-shadow:0 18px 48px rgba(0,0,0,.18)}',
    '#pe-head{padding:14px 18px;border-bottom:1px solid var(--bd-2);display:flex;align-items:center;gap:10px}',
    '#pe-head h3{margin:0;font-size:var(--fs-lg);font-weight:600;color:var(--n-900)}',
    '#pe-close{margin-left:auto;border:0;background:transparent;font-size:20px;color:var(--n-500);cursor:pointer;line-height:1}',
    '#pe-body{padding:16px 18px;overflow:auto;flex:1}',
    '#pe-foot{padding:12px 18px;border-top:1px solid var(--bd-2);display:flex;gap:8px;align-items:center}',
    '#pe-msg{font-size:var(--fs-sm);flex:1}',
    '#pe-msg.err{color:var(--red-600)}#pe-msg.ok{color:var(--green-900)}',
    '.pe-f{margin-bottom:14px}',
    '.pe-f>label{display:block;font-size:var(--fs-sm);font-weight:500;color:var(--n-800);margin-bottom:5px}',
    '.pe-f input[type=text],.pe-f textarea{width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid var(--bd-2);border-radius:var(--r-md);font-size:var(--fs-md);font-family:inherit;color:var(--n-900)}',
    '.pe-f textarea{resize:vertical;min-height:56px;line-height:1.6}',
    '.pe-hint{font-size:var(--fs-xs);color:var(--n-500);margin-top:4px}',
    '.pe-row{display:flex;gap:7px;align-items:flex-start;margin-bottom:7px}',
    '.pe-row .n{flex:0 0 20px;height:30px;display:flex;align-items:center;justify-content:center;color:var(--n-500);font-size:var(--fs-xs)}',
    '.pe-row input{flex:1;min-width:0}',
    '.pe-row .note{flex:0 0 168px}',
    '.pe-del{flex:0 0 auto;border:1px solid var(--bd-2);background:var(--n-00);border-radius:var(--r-sm);width:28px;height:30px;cursor:pointer;color:var(--n-500)}',
    '.pe-kv{display:flex;gap:7px;margin-bottom:6px;align-items:center}',
    '.pe-kv select{flex:0 0 140px;padding:6px 8px;border:1px solid var(--bd-2);border-radius:var(--r-md);font-size:var(--fs-sm);font-family:inherit}',
    '.pe-kv input{flex:1;min-width:0}',
    '.pe-sec{font-size:var(--fs-sm);font-weight:600;color:var(--n-800);margin:18px 0 8px;padding-top:14px;border-top:1px solid var(--bd-1)}',
    '.pe-sec:first-child{border-top:0;padding-top:0;margin-top:0}',
    '.pe-add{border:1px dashed var(--bd-3);background:transparent;border-radius:var(--r-md);padding:6px 10px;font-size:var(--fs-sm);color:var(--n-600);cursor:pointer;font-family:inherit}',
    '.pe-add:hover{border-color:var(--brand);color:var(--brand-strong)}'
  ].join('');

  var state = null, fields = [];

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function el(id) { return document.getElementById(id); }

  function fieldSelect(selected) {
    return '<select>' + fields.map(function (f) {
      return '<option value="' + f + '"' + (f === selected ? ' selected' : '') + '>' + f + '</option>';
    }).join('') + '</select>';
  }

  function subRow(index, text, note) {
    return '<div class="pe-row"><div class="n">' + index + '</div>'
      + '<input type="text" class="s-text" value="' + esc(text || '') + '" placeholder="这一小步做什么">'
      + '<input type="text" class="s-note note" value="' + esc(note || '') + '" placeholder="备注（可空）">'
      + '<button class="pe-del" title="删除">×</button></div>';
  }
  function kvRow(key, value) {
    return '<div class="pe-kv">' + fieldSelect(key)
      + '<input type="text" class="v" value="' + esc(value || '') + '" placeholder="方案规定的值">'
      + '<button class="pe-del" title="删除">×</button></div>';
  }
  function mustRow(key, prompt) {
    return '<div class="pe-kv">' + fieldSelect(key)
      + '<input type="text" class="p" value="' + esc(prompt || '') + '" placeholder="缺失时怎么问学生">'
      + '<button class="pe-del" title="删除">×</button></div>';
  }

  function bindDelete(root) {
    Array.prototype.forEach.call(root.querySelectorAll('.pe-del'), function (b) {
      b.onclick = function () { b.parentNode.remove(); renumber(); };
    });
  }
  function renumber() {
    Array.prototype.forEach.call(el('pe-subs').querySelectorAll('.pe-row .n'), function (n, i) {
      n.textContent = i + 1;
    });
  }

  function render() {
    var s = state.step;
    el('pe-title-text').textContent = '编辑第 ' + s.number + ' 步 · ' + state.protocol.title;
    el('pe-body').innerHTML =
      '<div class="pe-sec">基本信息</div>'
      + '<div class="pe-f"><label>步骤标题</label><input type="text" id="pe-title" value="' + esc(s.title) + '"></div>'
      + '<div class="pe-f"><label>步骤说明</label><textarea id="pe-instr">' + esc(s.instruction) + '</textarea></div>'
      + '<div class="pe-f"><label>安全提示（可空）</label><input type="text" id="pe-hazard" value="' + esc(s.hazard_note || '') + '"></div>'
      + '<div class="pe-sec">操作小步</div>'
      + '<div id="pe-subs">' + (s.substeps || []).map(function (x, i) { return subRow(i + 1, x.text, x.note); }).join('') + '</div>'
      + '<button class="pe-add" id="pe-add-sub">+ 添加小步</button>'
      + '<div class="pe-sec">方案已定的值</div>'
      + '<div class="pe-hint" style="margin-bottom:8px">方案作者写死的目标值，系统永远不会拿这些去追问学生。</div>'
      + '<div id="pe-vals">' + Object.keys(s.protocol_values).map(function (k) { return kvRow(k, s.protocol_values[k]); }).join('') + '</div>'
      + '<button class="pe-add" id="pe-add-val">+ 添加</button>'
      + '<div class="pe-sec">现场必测字段与追问话术</div>'
      + '<div class="pe-hint" style="margin-bottom:8px">只有现场才能产生的实测值。学生没说时，系统按下面的话术追问。</div>'
      + '<div id="pe-must">' + (s.must_record || []).map(function (k) {
          return mustRow(k, (state.step.field_prompts || {})[k]); }).join('') + '</div>'
      + '<button class="pe-add" id="pe-add-must">+ 添加</button>';

    el('pe-add-sub').onclick = function () {
      el('pe-subs').insertAdjacentHTML('beforeend', subRow(el('pe-subs').children.length + 1, '', ''));
      bindDelete(el('pe-subs'));
    };
    el('pe-add-val').onclick = function () {
      el('pe-vals').insertAdjacentHTML('beforeend', kvRow(fields[0], ''));
      bindDelete(el('pe-vals'));
    };
    el('pe-add-must').onclick = function () {
      el('pe-must').insertAdjacentHTML('beforeend', mustRow(fields[0], ''));
      bindDelete(el('pe-must'));
    };
    bindDelete(el('pe-body'));
  }

  function collect() {
    var subs = [];
    Array.prototype.forEach.call(el('pe-subs').querySelectorAll('.pe-row'), function (row) {
      var text = row.querySelector('.s-text').value.trim();
      if (text) subs.push({ text: text, note: row.querySelector('.s-note').value.trim() || null });
    });
    var values = {};
    Array.prototype.forEach.call(el('pe-vals').querySelectorAll('.pe-kv'), function (row) {
      var key = row.querySelector('select').value, value = row.querySelector('.v').value.trim();
      if (key && value) values[key] = value;
    });
    var must = [], prompts = {};
    Array.prototype.forEach.call(el('pe-must').querySelectorAll('.pe-kv'), function (row) {
      var key = row.querySelector('select').value, prompt = row.querySelector('.p').value.trim();
      if (!key || must.indexOf(key) >= 0) return;
      must.push(key);
      if (prompt) prompts[key] = prompt;
    });
    return {
      protocol_id: state.protocol.id,
      step_number: state.step.number,
      title: el('pe-title').value.trim(),
      instruction: el('pe-instr').value.trim(),
      hazard_note: el('pe-hazard').value.trim() || null,
      protocol_values: values,
      must_record: must,
      field_prompts: prompts,
      substeps: subs
    };
  }

  function msg(ok, text) {
    var box = el('pe-msg');
    box.className = ok ? 'ok' : 'err';
    box.textContent = text;
  }

  function save() {
    var button = el('pe-save');
    button.disabled = true;
    msg(true, '正在校验并保存…');
    fetch('/protocols/step', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect())
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, data: d }; });
    }).then(function (res) {
      if (!res.ok) { msg(false, res.data.detail || '保存失败'); return; }
      msg(true, '已保存并生效');
      if (window.runReload) window.runReload();
      setTimeout(close, 550);
    }).catch(function (err) {
      msg(false, String(err));
    }).then(function () { button.disabled = false; });
  }

  function close() { el('pe-mask').classList.remove('on'); }

  window.openProtocolEditor = function () {
    Promise.all([
      fetch('/protocols/session').then(function (r) { return r.json(); }),
      fetch('/protocols/entity-fields').then(function (r) { return r.json(); })
    ]).then(function (out) {
      state = out[0];
      fields = out[1].fields || [];
      if (state.mode !== 'protocol') { alert('请先选择一份实验方案'); return; }
      render();
      msg(true, '');
      el('pe-mask').classList.add('on');
    });
  };

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
    var mask = document.createElement('div');
    mask.id = 'pe-mask';
    mask.innerHTML = '<div id="pe">'
      + '<div id="pe-head"><h3 id="pe-title-text">编辑步骤</h3><button id="pe-close">×</button></div>'
      + '<div id="pe-body"></div>'
      + '<div id="pe-foot"><span id="pe-msg"></span>'
      + '<button class="sh-btn" id="pe-add-step">新增步骤</button>'
      + '<button class="sh-btn" id="pe-cancel">取消</button>'
      + '<button class="sh-btn primary" id="pe-save">保存</button></div></div>';
    document.body.appendChild(mask);
    el('pe-close').onclick = close;
    el('pe-cancel').onclick = close;
    el('pe-save').onclick = save;
    el('pe-add-step').onclick = function () {
      var title = prompt('新步骤标题');
      if (!title) return;
      fetch('/protocols/step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ protocol_id: state.protocol.id, title: title, instruction: '请补充步骤说明', must_record: [], terms: [] })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(function (res) {
        if (!res.ok) { alert(res.d.detail || '新增失败'); return; }
        close();
        if (window.runReload) window.runReload();
      });
    };
    mask.onclick = function (e) { if (e.target.id === 'pe-mask') close(); };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
