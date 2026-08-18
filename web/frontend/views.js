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
        + '<div class="p-card" data-id="" style="background:#fff;border:1px solid '
        + (session && session.mode === 'free' ? '#2563eb' : '#e2e8f0')
        + ';border-radius:12px;padding:15px 17px;margin-bottom:11px;cursor:pointer">'
        + '<div style="font-weight:600;color:#0f172a">自由记录模式</div>'
        + '<div style="color:#64748b;font-size:12px;margin-top:4px">不按方案，只做记录，不产生方案性追问</div></div>'
        + cards
        + '<div style="margin-top:18px;border-top:1px dashed #cbd5e1;padding-top:14px">'
        + '<div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:8px">新增方案</div>'
        + '<textarea id="protocol-text" rows="3" style="width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--bd-2);border-radius:8px;font-size:13px;margin-bottom:8px" placeholder="粘贴实验步骤文字，例如：配制 100mL 0.1M pH7.4 磷酸盐缓冲液，先称量磷酸盐，再溶解、调 pH、定容、混匀"></textarea>'
        + '<button class="sh-btn primary" id="ai-protocol-text-btn">AI 分析文字成方案</button>'
        + '<input type="file" id="protocol-file" accept=".json,.pdf,.png,.jpg,.jpeg" style="margin-left:10px;font-size:12px">'
        + '<span id="protocol-file-msg" style="color:#64748b;font-size:12px;margin-left:10px"></span>'
        + '<span style="color:#94a3b8;font-size:12px;margin-left:10px">文件自动识别：JSON 直接入库；PDF/图片走 OCR 识别成方案</span></div>'
        + '<div id="ai-draft-box"></div>'
        + '<div id="ocr-draft-box"></div>'
        + '</div>';
      var fileInput = host.querySelector('#protocol-file');
      if (fileInput) fileInput.onchange = function () {
        var file = fileInput.files && fileInput.files[0];
        var msg = host.querySelector('#protocol-file-msg');
        var box = host.querySelector('#ocr-draft-box');
        if (!file) return;
        var name = (file.name || '').toLowerCase();
        if (name.endsWith('.json')) {
          msg.textContent = 'JSON 上传中…';
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
          reader.readAsText(file);
          return;
        }
        if (/\.(pdf|png|jpg|jpeg)$/.test(name)) {
          msg.textContent = 'OCR 识别中，可能需要 1-2 分钟…';
          box.innerHTML = '';
          var form = new FormData();
          form.append('file', file);
          fetch('/protocols/upload-file', { method: 'POST', body: form }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
          }).then(function (res) {
            if (!res.ok) { msg.textContent = res.d.detail || '识别失败'; return; }
            var drafts = res.d.drafts || [];
            msg.textContent = '识别出 ' + drafts.length + ' 个实验，请逐个确认保存';
            box.innerHTML = drafts.map(function (draft, index) {
              return '<pre style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;white-space:pre-wrap;font-size:12px;margin-top:10px">'
                + esc(JSON.stringify(draft, null, 2)) + '</pre>'
                + '<div style="margin-top:8px"><button class="sh-btn primary" data-ocr-save="' + index + '">确认保存此方案</button></div>';
            }).join('');
            Array.prototype.forEach.call(box.querySelectorAll('[data-ocr-save]'), function (btn) {
              btn.onclick = function () {
                btn.disabled = true;
                api('/protocols/save-draft', 'POST', { protocol: drafts[parseInt(btn.dataset.ocrSave, 10)] }).then(function (saved) {
                  if (saved && saved.detail) { btn.textContent = '保存失败：' + saved.detail; btn.disabled = false; return; }
                  btn.textContent = '已保存';
                  window.shellShow('protocols');
                });
              };
            });
          }).catch(function (e) { msg.textContent = '识别失败：' + e.message; });
          return;
        }
        msg.textContent = '不支持的文件类型';
      };

      Array.prototype.forEach.call(host.querySelectorAll('.p-card'), function (card) {
        card.onclick = function () {
          if (!card.dataset.id) {
            api('/protocols/session', 'POST', { protocol_id: null }).then(function () {
              refreshStatus();
              window.shellShow('run');
            });
            return;
          }
          showProtocolDetail(host, card.dataset.id);
        };
      });

      function showProtocolDetail(host, protocolId) {
        api('/protocols/' + encodeURIComponent(protocolId)).then(function (d) {
          var steps = (d.steps || []).map(function (s) {
            var values = Object.keys(s.protocol_values || {}).map(function (k) {
              return '<span style="background:#e0e7ff;color:#3730a3;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;display:inline-block;font-size:11px">'
                + esc(k) + '=' + esc(s.protocol_values[k]) + '</span>';
            }).join('');
            var must = (s.must_record || []).join('、') || '无';
            var safety = (s.safety || []).map(function (x) {
              return '<div style="margin-top:6px;color:#b91c1c;font-size:12px">⚠ ' + esc(x.name) + '：' + esc((x.statements || []).join('；')) + '</div>';
            }).join('');
            return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;margin-bottom:10px">'
              + '<div style="font-weight:600;color:#0f172a;margin-bottom:6px">第 ' + s.number + ' 步 · ' + esc(s.title) + '</div>'
              + '<div style="color:#334155;font-size:13px;line-height:1.7">' + esc(s.instruction) + '</div>'
              + (values ? '<div style="margin-top:8px">方案已定：' + values + '</div>' : '')
              + '<div style="margin-top:8px;color:#64748b;font-size:12px">现场必测：' + esc(must) + '</div>'
              + (s.hazard_note ? '<div style="margin-top:8px;color:#b45309;font-size:12px">方案提示：' + esc(s.hazard_note) + '</div>' : '')
              + safety
              + '</div>';
          }).join('');
          var preps = (d.prep_requirements || []).map(function (p) {
            return '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:9px 12px;margin-bottom:8px">'
              + '<b>' + esc(p.name_zh) + '</b> · ' + esc(p.target_concentration || '工作液')
              + '<div style="color:#475569;font-size:12px;margin-top:3px">' + esc(p.purpose) + '</div></div>';
          }).join('');
          host.innerHTML = '<div style="max-width:820px">'
            + '<button class="sh-btn" id="protocol-back">← 返回方案列表</button>'
            + '<div style="margin:14px 0 4px;font-size:18px;font-weight:700;color:#0f172a">' + esc(d.protocol.title) + '</div>'
            + '<div style="color:#64748b;font-size:12px;margin-bottom:14px">' + esc(d.protocol.source) + ' · 共 ' + d.protocol.total_steps + ' 步 · v' + esc(d.protocol.version) + '</div>'
            + '<div style="margin-bottom:14px"><button class="sh-btn primary" id="protocol-select-detail">选择此方案开始实验</button>'
            + '<button class="sh-btn" id="protocol-edit-detail" style="margin-left:8px">编辑当前步骤</button></div>'
            + (preps ? '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:0 0 8px">实验前准备</div>' + preps : '')
            + '<div style="font-size:13px;font-weight:700;color:#0f172a;margin:10px 0 8px">实验步骤</div>'
            + steps + '</div>';
          host.querySelector('#protocol-back').onclick = function () { window.shellShow('protocols'); };
          host.querySelector('#protocol-select-detail').onclick = function () {
            api('/protocols/session', 'POST', { protocol_id: protocolId }).then(function () {
              refreshStatus();
              window.shellShow('run');
              if (window.runReload) window.runReload();
            });
          };
          host.querySelector('#protocol-edit-detail').onclick = function () {
            window.shellShow('run');
            setTimeout(function () { if (window.openProtocolEditor) window.openProtocolEditor(); }, 300);
          };
        }).catch(function (err) {
          host.innerHTML = '<div style="color:#b91c1c;font-size:13px">加载方案详情失败：' + esc(err.message || err) + '</div>';
        });
      }
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
      var cards = (d.reagents || []).map(function (r) {
        return '<div class="reagent-card" data-name="' + esc(r.name) + '" style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer">'
          + '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center"><b>' + esc(r.name) + '</b>'
          + (r.critical
              ? '<span style="background:#fee2e2;color:#b91c1c;border-radius:5px;padding:2px 8px;font-size:11px">高危 ' + (r.codes || []).join('/') + '</span>'
              : '<span style="color:#94a3b8;font-size:12px">无高危项</span>') + '</div>'
          + '<div style="color:#64748b;font-size:12px;margin-top:5px">CAS ' + esc(r.cas || '—') + ' · ' + esc(r.formula || '') + '</div></div>';
      }).join('');
      host.innerHTML = '<div style="max-width:860px">'
        + '<div style="color:#64748b;font-size:12px;line-height:1.7;margin-bottom:14px">共 ' + d.count + ' 种试剂。' + esc(d.note) + '</div>'
        + cards + '</div>';

      function showReagentDetail(item) {
        var statements = (item.statements || []).map(function (s) {
          return '<div style="padding:5px 0;border-bottom:1px solid #f1f5f9;color:#334155;font-size:13px">' + esc(s) + '</div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px">无 GHS 危险性说明记录</div>';
        var critical = (item.critical_statements || []).map(function (s) {
          return '<div style="padding:4px 0;color:#b91c1c;font-size:12px">⚠ ' + esc(s) + '</div>';
        }).join('') || '<div style="color:#94a3b8;font-size:12px">无高危项</div>';
        host.innerHTML = '<div style="max-width:760px">'
          + '<button class="sh-btn" id="reagent-back">← 返回试剂列表</button>'
          + '<div style="margin:14px 0 4px;font-size:18px;font-weight:700;color:#0f172a">' + esc(item.name) + '</div>'
          + '<div style="color:#64748b;font-size:12px;margin-bottom:14px">' + esc(item.name_en || '') + ' · CAS ' + esc(item.cas || '—') + ' · ' + esc(item.formula || '') + ' · ' + esc(item.signal_word || '') + '</div>'
          + '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:13px 15px;margin-bottom:12px"><div style="font-size:13px;font-weight:700;color:#0f172a;margin-bottom:6px">GHS 危险性说明</div>' + statements + '</div>'
          + '<div style="background:#fff;border:1px solid #fee2e2;border-radius:12px;padding:13px 15px;margin-bottom:12px"><div style="font-size:13px;font-weight:700;color:#b91c1c;margin-bottom:6px">现场重点提醒</div>' + critical + '</div>'
          + '<div style="font-size:12px;color:#94a3b8">复核状态：' + esc(item.review_status || 'UNREVIEWED') + (item.source_url ? ' · <a href="' + esc(item.source_url) + '" target="_blank">PubChem 来源</a>' : '') + '</div>'
          + '</div>';
        host.querySelector('#reagent-back').onclick = function () { window.shellShow('reagents'); };
      }

      Array.prototype.forEach.call(host.querySelectorAll('.reagent-card'), function (card) {
        card.onclick = function () {
          var item = (d.reagents || []).filter(function (r) { return r.name === card.dataset.name; })[0];
          if (item) showReagentDetail(item);
        };
      });
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
