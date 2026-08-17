/* 试剂配置库页面：查看配方、上传用户自己的 JSON 配置库。 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function renderPrep(p) {
    var steps = (p.steps || []).map(function (s, i) {
      return '<div style="margin:4px 0 0 18px;color:#475569;font-size:13px">' + (i + 1) + '. ' + esc(s) + '</div>';
    }).join('');
    var safety = (p.safety || []).map(function (s) {
      return '<div class="lab-hazard" style="margin-top:6px">⚠ ' + esc(s.name) + '：' + esc((s.statements || []).join('；')) + '</div>';
    }).join('');
    var badge = p.review_status === 'REVIEWED' ? '<span style="color:#16a34a">已复核</span>' : '<span style="color:#d97706">未复核</span>';
    return '<div style="background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:12px 14px;margin-bottom:10px">'
      + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b>' + esc(p.name_zh) + '</b><span style="font-size:12px">' + badge + '</span></div>'
      + '<div style="color:#64748b;font-size:13px;margin-top:4px">' + esc(p.purpose) + '</div>'
      + '<div style="color:#334155;font-size:13px;margin-top:6px">目标：' + esc(p.target_concentration || '未指定') + '；体积：' + esc(p.target_volume || '按需') + '；溶剂：' + esc(p.solvent || '未指定') + '</div>'
      + steps
      + safety
      + (p.source_url ? '<div style="margin-top:6px;font-size:12px"><a href="' + esc(p.source_url) + '" target="_blank">来源</a> · ' + esc(p.source) + '</div>' : '<div style="margin-top:6px;font-size:12px;color:#94a3b8">来源：' + esc(p.source) + '</div>')
      + '</div>';
  }

  window.shellRegisterView('reagent_prep', function (host) {
    host.innerHTML = '<h3>试剂配置库'
      + '<input type="file" id="prep-file" accept=".json,application/json" style="margin-left:12px;font-size:12px">'
      + '<button class="sh-btn" id="prep-upload" style="margin-left:8px">上传 JSON</button>'
      + '<span id="prep-upload-msg" style="margin-left:8px;font-size:12px;color:#64748b"></span></h3>'
      + '<div style="color:#64748b;font-size:12px;margin:8px 0 12px">JSON 格式：{"reagent_preps":[{...}]}，字段见契约说明。上传会严格校验，不通过不落盘。</div>'
      + '<div id="prep-list" style="margin-top:12px">加载中…</div>';

    function load() {
      fetch('/reagent-prep').then(function (r) { return r.json(); }).then(function (d) {
        host.querySelector('#prep-list').innerHTML = (d.items || []).map(renderPrep).join('') || '<div style="color:#94a3b8">暂无配置。</div>';
      });
    }

    host.querySelector('#prep-upload').onclick = function () {
      var input = host.querySelector('#prep-file');
      var msg = host.querySelector('#prep-upload-msg');
      if (!input.files || !input.files[0]) { msg.textContent = '请先选择 JSON 文件'; return; }
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          var payload = { reagent_preps: data.reagent_preps || [data] };
          fetch('/reagent-prep/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
          }).then(function (res) {
            if (!res.ok) { msg.textContent = res.d.detail || '上传失败'; return; }
            msg.textContent = '已新增 ' + res.d.added + ' 条';
            load();
          }).catch(function (e) { msg.textContent = '上传失败：' + e.message; });
        } catch (e) {
          msg.textContent = 'JSON 解析失败：' + e.message;
        }
      };
      reader.readAsText(input.files[0]);
    };

    load();
  });
})();
