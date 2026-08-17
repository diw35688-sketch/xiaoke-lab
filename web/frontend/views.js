// 把原先散落的悬浮面板，改造成应用外壳里的正式页面与详情区内容。
(function () {
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

  var session = null;

  // ---------- 顶栏状态 ----------
  function refreshStatus() {
    Promise.all([api('/settings'), api('/protocols/session')]).then(function (out) {
      var s = out[0], p = out[1];
      session = p;
      var bits = [];
      bits.push(s.ready
        ? '<span class="sh-pill ok">模型已配置</span>'
        : '<span class="sh-pill warn">未配置模型</span>');
      bits.push(p.mode === 'protocol'
        ? '<span class="sh-pill">' + esc(p.protocol.title) + ' · 第 ' + p.step.number + '/' + p.protocol.total_steps + ' 步</span>'
        : '<span class="sh-pill">自由记录模式</span>');
      window.shellStatus(bits.join(''));
      if (window.runReload) window.runReload();
    }).catch(function () {});
  }
  window.shellRefreshStatus = refreshStatus;

  // ---------- 实验方案页 ----------
  window.shellRegisterView('protocols', function (host) {
    api('/protocols').then(function (d) {
      var cards = (d.protocols || []).map(function (p) {
        var on = session && session.mode === 'protocol' && session.protocol.id === p.id;
        return '<div class="p-card" data-id="' + p.id + '" style="background:#fff;border:1px solid '
          + (on ? '#2563eb' : '#e2e8f0') + ';border-radius:12px;padding:15px 17px;margin-bottom:11px;cursor:pointer'
          + (on ? ';box-shadow:0 0 0 2px #bfdbfe' : '') + '">'
          + '<div style="font-weight:600;color:#0f172a;margin-bottom:5px">' + esc(p.title)
          + (on ? '<span style="color:#2563eb;font-size:12px;margin-left:8px">进行中</span>' : '') + '</div>'
          + '<div style="color:#64748b;font-size:12px;line-height:1.6">共 ' + p.total_steps + ' 步 · ' + esc(p.source) + '</div></div>';
      }).join('');
      host.innerHTML = '<div style="max-width:760px">'
          + '<div style="margin-bottom:14px"><textarea id="protocol-text" rows="3" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--bd-2);border-radius:8px;font-size:13px;margin-bottom:8px" placeholder="粘贴实验步骤文字，例如：配制 100mL 0.1M pH7.4 磷酸盐缓冲液，先称量磷酸盐，再溶解、调 pH、定容、混匀"></textarea>'
          + '<button class="sh-btn primary" id="ai-protocol-text-btn">AI 分析文字成方案</button>'
          + '<button class="sh-btn" id="ai-protocol-btn">AI 生成方案（弹窗描述）</button>'
          + '<input type="file" id="protocol-file" accept=".json,application/json" style="margin-left:10px;font-size:12px">'
          + '<button class="sh-btn" id="protocol-upload-btn" style="margin-left:6px">上传 JSON</button>'
          + '<span id="protocol-upload-msg" style="color:#64748b;font-size:12px;margin-left:10px"></span>'
          + '<span style="color:#94a3b8;font-size:12px;margin-left:10px">JSON：{"protocols":[{...}]}</span></div>'
          + '<div id="ai-draft-box"></div>'
        + '<div class="p-card" data-id="" style="background:#fff;border:1px solid '
        + (session && session.mode === 'free' ? '#2563eb' : '#e2e8f0')
        + ';border-radius:12px;padding:15px 17px;margin-bottom:11px;cursor:pointer">'
        + '<div style="font-weight:600;color:#0f172a">自由记录模式</div>'
        + '<div style="color:#64748b;font-size:12px;margin-top:4px">不按方案，只做记录，不产生方案性追问</div></div>'
        + cards + '</div>';
      var uploadBtn = host.querySelector('#protocol-upload-btn');
      if (uploadBtn) uploadBtn.onclick = function () {
        var input = host.querySelector('#protocol-file');
        var msg = host.querySelector('#protocol-upload-msg');
        if (!input.files || !input.files[0]) { msg.textContent = '请先选择 JSON 文件'; return; }
        var reader = new FileReader();
        reader.onload = function () {
          try {
            var data = JSON.parse(reader.result);
            var payload = { protocols: data.protocols || [data] };
            api('/protocols/upload', 'POST', payload).then(function (res) {
              if (res && res.detail) { msg.textContent = '上传失败：' + res.detail; return; }
              msg.textContent = '已新增 ' + (res.added || 0) + ' 份方案';
              window.shellShow('protocols');
            }).catch(function (e) { msg.textContent = '上传失败：' + e.message; });
          } catch (e) { msg.textContent = 'JSON 解析失败：' + e.message; }
        };
        reader.readAsText(input.files[0]);
      };

      Array.prototype.forEach.call(host.querySelectorAll('.p-card'), function (card) {
        card.onclick = function () {
          api('/protocols/session', 'POST', { protocol_id: card.dataset.id || null }).then(function () {
            refreshStatus();
            window.shellShow('protocols');
            if (window.labStepsReload) window.labStepsReload();
          });
        };
      });
        var aiTextBtn = host.querySelector('#ai-protocol-text-btn');
        if (aiTextBtn) aiTextBtn.onclick = function () {
          var text = host.querySelector('#protocol-text').value.trim();
          if (!text) { alert('请先粘贴实验步骤文字'); return; }
          var box = host.querySelector('#ai-draft-box');
          box.innerHTML = '<p style="color:#64748b;font-size:12px">AI 正在分析文字…</p>';
          api('/protocols/ai-draft', 'POST', { text: text }).then(function (d) {
            if (d && d.detail) throw new Error(d.detail);
            box.innerHTML = '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px">'
              + esc(JSON.stringify(d, null, 2)) + '</pre>'
              + '<div style="margin-top:10px"><button class="sh-btn primary" id="ai-draft-save">确认保存此方案</button></div>'
              + '<p id="ai-draft-msg" style="color:#64748b;font-size:12px;margin-top:8px"></p>';
            host.querySelector('#ai-draft-save').onclick = function () {
              api('/protocols/save-draft', 'POST', { protocol: d }).then(function (res) {
                var msg = host.querySelector('#ai-draft-msg');
                if (res && res.detail) { msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + res.detail; return; }
                msg.style.color = '#15803d'; msg.textContent = '方案已保存，已自动识别关联试剂';
                window.shellShow('protocols');
              });
            };
          }).catch(function (err) {
            box.innerHTML = '<p style="color:#c2410c;font-size:12px">AI 分析失败：' + (err.message || err) + '</p>';
          });
        };

        var aiBtn = host.querySelector('#ai-protocol-btn');
        if (aiBtn) aiBtn.onclick = function () {
          var text = prompt('用自然语言描述你想做的实验，例如：配制100mL 0.1M pH7.4磷酸盐缓冲液');
          if (!text) return;
          var box = host.querySelector('#ai-draft-box');
          box.innerHTML = '<p style="color:#64748b;font-size:12px">AI 正在生成方案草稿…</p>';
          api('/protocols/ai-draft', 'POST', { text: text }).then(function (d) {
            if (d && d.detail) throw new Error(d.detail);
            box.innerHTML = '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px">'
              + esc(JSON.stringify(d, null, 2)) + '</pre>'
              + '<div style="margin-top:10px"><button class="sh-btn primary" id="ai-draft-save">确认保存此方案</button><span style="color:#94a3b8;font-size:12px;margin-left:10px">保存前会经过严格契约校验</span></div>'
                + '<p id="ai-draft-msg" style="color:#64748b;font-size:12px;margin-top:8px"></p>';
              var saveBtn = host.querySelector('#ai-draft-save');
              saveBtn.onclick = function () {
                saveBtn.disabled = true;
                api('/protocols/save-draft', 'POST', { protocol: d }).then(function (res) {
                  var msg = host.querySelector('#ai-draft-msg');
                  if (res && res.detail) { msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + res.detail; return; }
                  msg.style.color = '#15803d'; msg.textContent = '方案已保存';
                  if (window.shellRegisterView) window.shellShow('protocols');
                  if (window.runReload) window.runReload();
                  refreshStatus();
                }).catch(function (err) {
                  var msg = host.querySelector('#ai-draft-msg');
                  msg.style.color = '#c2410c'; msg.textContent = '保存失败：' + (err.message || '未知错误');
                }).then(function () { saveBtn.disabled = false; });
              };
          }).catch(function (err) {
            box.innerHTML = '<p style="color:#c2410c;font-size:12px">生成失败：' + esc(err.message || '未知错误') + '</p>';
          });
        };
    });
  });

  // ---------- 试剂安全库页 ----------
  window.shellRegisterView('reagents', function (host) {
    api('/protocols/reagents').then(function (d) {
      var rows = (d.reagents || []).map(function (r) {
        return '<tr style="border-bottom:1px solid #f1f5f9">'
          + '<td style="padding:9px 10px;font-weight:500;color:#0f172a">' + esc(r.name) + '</td>'
          + '<td style="padding:9px 10px;color:#64748b;font-size:12px">' + esc(r.cas || '—') + '</td>'
          + '<td style="padding:9px 10px">' + (r.critical
              ? '<span style="background:#fee2e2;color:#b91c1c;border-radius:5px;padding:2px 8px;font-size:11px">高危 ' + (r.codes || []).join('/') + '</span>'
              : '<span style="color:#94a3b8;font-size:12px">无高危项</span>') + '</td></tr>';
      }).join('');
      host.innerHTML = '<div style="max-width:860px">'
        + '<div style="color:#64748b;font-size:12px;line-height:1.7;margin-bottom:14px">共 ' + d.count + ' 种试剂。' + esc(d.note) + '</div>'
        + '<table style="width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:13px">'
        + '<thead><tr style="background:#f8fafc;color:#475569;font-size:12px">'
        + '<th style="text-align:left;padding:10px">试剂</th><th style="text-align:left;padding:10px">CAS</th>'
        + '<th style="text-align:left;padding:10px">危险性</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
    });
  });

  // ---------- 本次记录页 ----------
  window.shellRegisterView('records', function (host) {
    api('/record/history').then(function (d) {
      if (!d.count) {
        host.innerHTML = '<div style="color:#94a3b8;font-size:13px">本次会话还没有记录。</div>';
        return;
      }
      host.innerHTML = '<div style="max-width:820px"><div style="color:#64748b;font-size:12px;margin-bottom:12px">会话 '
        + esc(d.session_id) + ' · 共 ' + d.count + ' 段</div>'
        + d.items.map(function (it) {
          var ents = Object.keys(it.entities || {}).map(function (k) {
            return '<span style="background:#e0e7ff;color:#3730a3;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;display:inline-block;font-size:11px">'
              + esc(k) + '=' + esc(it.entities[k]) + '</span>';
          }).join('') || '<span style="color:#94a3b8;font-size:12px">未抽到结构化字段</span>';
          var ev = it.evaluation || {};
          return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px;margin-bottom:11px">'
            + '<div style="font-size:12px;color:#94a3b8;margin-bottom:5px">第 ' + it.segment_id + ' 段 · ' + esc(it.at) + '</div>'
            + '<div style="color:#0f172a;margin-bottom:8px">' + esc(it.transcript) + '</div>'
            + '<div>' + ents + '</div>'
            + (ev.follow_up_required ? '<div style="background:#eff6ff;color:#1e40af;border-radius:8px;padding:9px 11px;margin-top:9px;font-size:12px">追问：'
                + esc(ev.follow_up_question) + '</div>' : '')
            + (ev.deviations || []).map(function (x) {
                return '<div style="background:#fff7ed;color:#c2410c;border-radius:8px;padding:9px 11px;margin-top:7px;font-size:12px">偏差：'
                  + esc(x.field) + ' 实际 ' + esc(x.actual_value) + '，方案 ' + esc(x.protocol_value) + '</div>';
              }).join('')
            + '</div>';
        }).join('') + '</div>';
    });
  });

  // ---------- 设置页：复用已有面板，改为内嵌 ----------
  window.shellRegisterView('settings', function (host) {
    host.innerHTML = '<div style="max-width:620px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px 22px" id="settings-inline"></div>';
    var modal = document.getElementById('settings-modal');
    if (modal) {
      var box = modal.querySelector('.settings-box');
      if (box) {
        box.style.boxShadow = 'none';
        box.style.maxHeight = 'none';
        box.style.width = '100%';
        var head = box.querySelector('.settings-head');
        if (head) head.style.display = 'none';
        document.getElementById('settings-inline').appendChild(box);
      }
    }
    if (window.__ttsAttach) window.__ttsAttach();
  });

  document.addEventListener('shell-ready', function () {
    refreshStatus();
    setInterval(refreshStatus, 5000);
  });
})();
