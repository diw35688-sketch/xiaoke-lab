/* 试剂配置库页面：查看配方、上传用户自己的 JSON 配置库。 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function renderPrep(p) {
    var badge = p.review_status === 'REVIEWED' ? '<span style="color:#16a34a">已复核</span>' : '<span style="color:#d97706">未复核</span>';
    return '<div class="prep-card" data-id="' + esc(p.reagent_prep_id) + '" style="background:var(--n-00,#fff);border:1px solid var(--bd-1,#e2e8f0);border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer">'
      + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b>' + esc(p.name_zh) + '</b><span style="font-size:12px">' + badge + '</span></div>'
      + '<div style="color:#64748b;font-size:13px;margin-top:4px">' + esc(p.purpose) + '</div>'
      + '<div style="color:#334155;font-size:13px;margin-top:6px">目标：' + esc(p.target_concentration || '未指定') + ' · 体积：' + esc(p.target_volume || '按需') + ' · 溶剂：' + esc(p.solvent || '未指定') + '</div>'
      + '</div>';
  }

  function showPrepDetail(host, prep) {
    var steps = (prep.steps || []).map(function (s, i) {
      return '<div style="margin:5px 0 0 18px;color:#475569;font-size:13px">' + (i + 1) + '. ' + esc(s) + '</div>';
    }).join('');
    var safety = (prep.safety || []).map(function (s) {
      return '<div style="margin-top:6px;color:#b91c1c;font-size:12px">⚠ ' + esc(s.name) + '：' + esc((s.statements || []).join('；')) + '</div>';
    }).join('');
    var badge = prep.review_status === 'REVIEWED' ? '<span style="color:#16a34a">已复核</span>' : '<span style="color:#d97706">未复核</span>';
    host.innerHTML = '<div style="max-width:820px">'
      + '<button class="sh-btn" id="prep-back">← 返回配置列表</button>'
      + '<div style="margin:14px 0 4px;font-size:18px;font-weight:700;color:#0f172a">' + esc(prep.name_zh) + '</div>'
      + '<div style="color:#64748b;font-size:12px;margin-bottom:14px">' + esc(prep.purpose) + ' · ' + badge + '</div>'
      + '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:12px">'
      + '<div style="color:#334155;font-size:13px;line-height:1.8">目标：' + esc(prep.target_concentration || '未指定') + '<br>体积：' + esc(prep.target_volume || '按需') + '<br>溶剂：' + esc(prep.solvent || '未指定') + '<br>保存：' + esc(prep.storage_condition || '未指定') + '<br>有效期：' + esc(prep.expiry || '未指定') + '</div></div>'
      + '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:10px 0 8px">配制步骤</div>'
      + '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:12px 15px">' + steps + '</div>'
      + (safety ? '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:12px 0 8px">安全提示</div><div style="background:#fff;border:1px solid #fee2e2;border-radius:12px;padding:12px 15px">' + safety + '</div>' : '')
      + '<div style="margin-top:12px;font-size:12px;color:#94a3b8">来源：' + esc(prep.source || '未注明') + (prep.source_url ? ' · <a href="' + esc(prep.source_url) + '" target="_blank">查看来源</a>' : '') + '</div>'
      + '</div>';
    host.querySelector('#prep-back').onclick = function () { window.shellShow('reagent_prep'); };
  }

  window.shellRegisterView('reagent_prep', function (host) {
    host.innerHTML = '<h3>试剂配置库'
      + '<input type="file" id="prep-file" accept=".json,application/json" style="margin-left:12px;font-size:12px">'
      + '<button class="sh-btn" id="prep-upload" style="margin-left:8px">上传 JSON</button>'
      + '<span id="prep-upload-msg" style="margin-left:8px;font-size:12px;color:#64748b"></span></h3>'
      + '<div style="color:#64748b;font-size:12px;margin:8px 0 6px">JSON 格式：{"reagent_preps":[{...}]}，字段见契约说明。上传会严格校验，不通过不落盘。</div>'
      + '<div style="margin:8px 0 12px"><button class="sh-btn primary" id="prep-chat-create">在右侧对话中创建试剂配置</button>'
      + '<span style="margin-left:8px;font-size:12px;color:#64748b">告诉 AI 浓度、体积、溶剂、保存条件即可</span></div>'
      + '<div id="prep-form-box" style="display:none;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:14px">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px">填写试剂配置信息</div>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">'
      + '<div><label style="font-size:12px;color:#475569">试剂名称</label><input id="pf-name" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：PBS 缓冲液"></div>'
      + '<div><label style="font-size:12px;color:#475569">目标浓度</label><input id="pf-conc" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：0.1 mol/L"></div>'
      + '<div><label style="font-size:12px;color:#475569">体积</label><input id="pf-vol" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：500 mL"></div>'
      + '<div><label style="font-size:12px;color:#475569">溶剂</label><input id="pf-solvent" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：超纯水 / DMSO"></div>'
      + '<div><label style="font-size:12px;color:#475569">保存条件</label><input id="pf-storage" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：4℃ 避光"></div>'
      + '<div><label style="font-size:12px;color:#475569">有效期</label><input id="pf-expiry" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：1 个月"></div>'
      + '<div style="grid-column:1 / -1"><label style="font-size:12px;color:#475569">用途</label><input id="pf-purpose" style="width:100%;margin-top:4px;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px" placeholder="例如：细胞洗涤、Western blot 转膜缓冲液"></div>'
      + '</div>'
      + '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">'
      + '<button class="sh-btn primary" id="pf-send">生成并发送</button>'
      + '<button class="sh-btn" id="pf-cancel">取消</button>'
      + '<span id="pf-msg" style="font-size:12px;color:#64748b"></span>'
      + '</div>'
      + '</div>'
      + '<div id="prep-list" style="margin-top:12px">加载中…</div>';

    function load() {
      fetch('/reagent-prep').then(function (r) { return r.json(); }).then(function (d) {
        host.querySelector('#prep-list').innerHTML = (d.items || []).map(renderPrep).join('') || '<div style="color:#94a3b8">暂无配置。</div>';
        Array.prototype.forEach.call(host.querySelectorAll('.prep-card'), function (card) {
          card.onclick = function () {
            var item = (d.items || []).filter(function (x) { return x.reagent_prep_id === card.dataset.id; })[0];
            if (item) showPrepDetail(host, item);
          };
        });
      });
    }

    host.querySelector('#prep-chat-create').onclick = function () {
      var box = host.querySelector('#prep-form-box');
      box.style.display = '';
      box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      var nameInput = host.querySelector('#pf-name');
      if (nameInput) nameInput.focus();
    };

    host.querySelector('#pf-send').onclick = function () {
      var parts = [];
      var name = (host.querySelector('#pf-name').value || '').trim();
      var conc = (host.querySelector('#pf-conc').value || '').trim();
      var vol = (host.querySelector('#pf-vol').value || '').trim();
      var solvent = (host.querySelector('#pf-solvent').value || '').trim();
      var storage = (host.querySelector('#pf-storage').value || '').trim();
      var expiry = (host.querySelector('#pf-expiry').value || '').trim();
      var purpose = (host.querySelector('#pf-purpose').value || '').trim();
      if (name) parts.push('试剂：' + name);
      if (conc) parts.push('浓度：' + conc);
      if (vol) parts.push('体积：' + vol);
      if (solvent) parts.push('溶剂：' + solvent);
      if (storage) parts.push('保存条件：' + storage);
      if (expiry) parts.push('有效期：' + expiry);
      if (purpose) parts.push('用途：' + purpose);
      if (!parts.length) { host.querySelector('#pf-msg').textContent = '请至少填写一项'; return; }
      var text = '请根据以下要求创建一条试剂配置：' + parts.join('，') + '。';
      var message = document.getElementById('message');
      if (message) {
        message.value = text;
        message.focus();
      }
      var sendBtn = document.getElementById('send-btn');
      if (sendBtn) sendBtn.click();
      host.querySelector('#prep-form-box').style.display = 'none';
    };

    host.querySelector('#pf-cancel').onclick = function () {
      host.querySelector('#prep-form-box').style.display = 'none';
    };

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
