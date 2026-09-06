// 模型设置面板：任何人都能在浏览器里配置模型，不需要碰服务器文件。
(function () {
  var PANEL_HTML = [
    '<div id="settings-modal" class="settings-mask">',
    '  <div class="settings-box">',
    '    <header class="settings-head"><h2>模型与语音服务</h2>',
    '      <button id="settings-close" title="close">x</button></header>',
    '    <div id="settings-status" class="settings-status"></div>',
    '    <div class="settings-section" data-section="model">',
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">文字模型</div>',
    '    <label class="settings-field"><span>服务商预设</span>',
    '      <div class="preset-row"><select id="settings-preset"></select>',
    '        <a id="settings-api-url" href="#" target="_blank" rel="noopener" class="api-link">获取 API</a></div>',
    '      <em>选择后自动填好地址和模型名，也可以选自定义手动填。</em></label>',
    '    <label class="settings-field"><span>接口地址 Base URL</span>',
    '      <input id="settings-base-url" type="text" /></label>',
    '    <label class="settings-field"><span>模型名称</span>',
    '      <div class="model-row"><input id="settings-model" type="text" list="settings-model-list" />',
    '        <button id="settings-fetch-models" class="ghost" type="button">拉取模型</button></div>',
    '      <datalist id="settings-model-list"></datalist>',
    '      <select id="settings-model-select" style="display:none;width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:9px;font-size:14px;font-family:inherit;margin-top:8px"></select>',
    '      <em id="settings-models-msg" style="display:block;font-style:normal;font-size:12px;color:#64748b;margin-top:5px"></em></label>',
    '    <label class="settings-field"><span>API 密钥</span>',
    '      <input id="settings-key" type="password" autocomplete="off" />',
    '      <em>密钥只保存在本机服务器，页面上始终以掩码显示。</em></label>',
    '    </div>',
    '    <div class="settings-section" data-section="doc">',
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">文档解析（MinerU / OCR）</div>',
    '    <label class="settings-field"><span>MinerU 密钥</span>',
    '      <input id="settings-mineru-key" type="password" autocomplete="off" placeholder="留空则使用主 LLM 密钥" /></label>',
    '    <label class="settings-field"><span>图片 OCR 模型</span>',
    '      <input id="settings-ocr-model" type="text" placeholder="unlimited-ocr" /></label>',
    '    <label class="settings-field"><span>图片 OCR 密钥</span>',
    '      <input id="settings-ocr-key" type="password" autocomplete="off" placeholder="留空则使用主 LLM 密钥" /></label>',
    '    </div>',
    '    <div class="settings-section" data-section="voice">',
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">语音模型</div>',
    '    <label class="settings-field settings-inline">',
    '      <input id="settings-tts" type="checkbox" />',
    '      <span>启用语音播报（需本机 TTS 服务在 8001 端口运行）</span></label>',
    '    <label class="settings-field settings-inline">',
    '      <input id="settings-voice-short" type="checkbox" />',
    '      <span>语音场景强制短回复（把回复控制在 50 字内）</span></label>',
    '    <label class="settings-field settings-inline">',
    '      <input id="settings-voice-no-think" type="checkbox" />',
    '      <span>语音场景禁用思考（降低延迟，不显示推理链）</span></label>',
    '    <label class="settings-field"><span style="display:flex;align-items:center;justify-content:space-between;gap:10px">DashScope API Key（Qwen Audio 实时语音）',
    '      <a class="api-link" href="https://bailian.console.aliyun.com/?apiKey=1#/api-key" target="_blank" rel="noopener" style="font-size:12px;padding:4px 10px">获取 Key ↗</a></span>',
    '      <input id="settings-dashscope-key" type="password" autocomplete="off" placeholder="与阿里百炼模型共用，已配置可留空" />',
    '      <em>DashScope 实时语音与上方“阿里百炼（通义）”模型使用同一个 API Key；在模型配置里填过就不用再填。</em></label>',
    '    <label class="settings-field"><span>实时语音模型</span>',
    '      <div class="model-row"><input id="settings-dashscope-model" type="text" list="settings-dashscope-model-list" value="qwen-audio-3.0-realtime-plus" />',
    '        <button id="settings-dashscope-pull" class="ghost" type="button">拉取模型</button></div>',
    '      <datalist id="settings-dashscope-model-list"></datalist>',
    '      <select id="settings-dashscope-model-select" style="display:none;width:100%;box-sizing:border-box;margin:-4px 0 10px;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;color:#0f172a;font-size:13px"></select>',
    '      <em>点“拉取模型”会用上面这个 DashScope Key 拉取可用模型，选择后保存。</em></label>',
    '    <div class="settings-qwen-row">',
    '      <button id="settings-qwen-start" class="ghost" type="button">启动 QwenAudio 实时语音</button>',
    '      <span id="settings-qwen-status" class="settings-qwen-status"></span></div>',
    '    </div>',
    '    <div class="settings-section" data-section="misc">',
    '    <label class="settings-field settings-inline">',
    '      <input id="settings-heartbeat-enabled" type="checkbox" checked />',
    '      <span>启用每日心跳（主动汇报今日实验 / 提醒）</span></label>',
    '    <label class="settings-field"><span>每日心跳时间</span>',
    '      <input id="settings-heartbeat-time" type="time" value="08:00" /></label>',
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">主人画像（可选，用于个性化规划）</div>',
    '    <label class="settings-field"><span>研究领域 / 方向</span>',
    '      <input id="settings-profile-field" type="text" placeholder="例如：分子生物学、免疫组化、材料合成" /></label>',
    '    <label class="settings-field"><span>常用方法 / 试剂</span>',
    '      <textarea id="settings-profile-methods" rows="2" placeholder="例如：Western blot、SDS-PAGE、酚氯仿提取"></textarea></label>',
    '    <label class="settings-field"><span>偏好 / 备注</span>',
    '      <textarea id="settings-profile-notes" rows="2" placeholder="例如：习惯晚上做实验、记录要详细、自动播报"></textarea></label>',
    '    </div>',
    '    <div class="settings-actions">',
    '      <button id="settings-test" class="ghost">测试连接</button>',
    '      <button id="settings-save" class="primary">保存并生效</button></div>',
    '    <p id="settings-result" class="settings-result"></p>',
    '  </div></div>'
  ].join('');

  var CSS = [
    '.settings-mask{position:fixed;inset:0;background:rgba(15,23,42,.55);display:none;align-items:center;justify-content:center;z-index:9999}',
    '.settings-mask.show{display:flex}',
    '.settings-box{background:#fff;border-radius:16px;padding:26px 28px;width:min(520px,92vw);max-height:88vh;overflow:auto;box-shadow:0 24px 60px rgba(15,23,42,.28)}',
    '.settings-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}',
    '.settings-head h2{margin:0;font-size:19px;color:#0f172a}',
    '#settings-close{border:0;background:transparent;font-size:24px;line-height:1;cursor:pointer;color:#94a3b8}',
    '.settings-status{font-size:13px;padding:9px 12px;border-radius:9px;margin-bottom:16px}',
    '.settings-status.ok{background:#ecfdf5;color:#047857}',
    '.settings-status.warn{background:#fff7ed;color:#c2410c}',
    '.settings-field{display:block;margin-bottom:15px}',
    '.settings-field>span{display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600}',
    '.settings-field input,.settings-field select,.settings-field textarea{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:9px;font-size:14px;font-family:inherit}',
    '.settings-field textarea{resize:vertical;min-height:52px}',
    '.settings-field em{display:block;font-style:normal;font-size:12px;color:#94a3b8;margin-top:5px}',
    '.settings-inline{display:flex;align-items:center;gap:9px}',
    '.settings-inline span{font-weight:400;font-size:13px;color:#334155;margin:0}',
    '.settings-inline input{width:auto}',
    '.settings-qwen-row{display:flex;align-items:center;gap:10px;margin-bottom:15px}',
    '.settings-qwen-row button{white-space:nowrap;padding:8px 14px;border-radius:9px;border:1px solid #cbd5e1;background:#fff;color:#334155;cursor:pointer;font-size:13px;font-family:inherit}',
    '.settings-qwen-status{font-size:12px;color:#64748b}',
    '.settings-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:20px}',
    '.settings-actions button{padding:9px 18px;border-radius:9px;font-size:14px;cursor:pointer;border:1px solid transparent;font-family:inherit}',
    '.preset-row{display:flex;gap:8px;align-items:center}',
    '.preset-row select{flex:1}',
    '.api-link{display:inline-flex;align-items:center;padding:8px 12px;border-radius:9px;border:1px solid #cbd5e1;background:#fff;color:#2563eb;text-decoration:none;font-size:13px;white-space:nowrap}',
    '.api-link:hover{border-color:#2563eb;background:#eff6ff}',
    '.model-row{display:flex;gap:8px}',
    '.model-row input{flex:1}',
    '.model-row button{white-space:nowrap;padding:9px 12px;border-radius:9px;border:1px solid #cbd5e1;background:#fff;color:#334155;cursor:pointer;font-size:13px;font-family:inherit}',
    '.settings-actions .ghost{background:#fff;border-color:#cbd5e1;color:#334155}',
    '.settings-actions .primary{background:#2563eb;color:#fff}',
    '.settings-result{font-size:13px;margin:14px 0 0;min-height:19px}',
    '.settings-result.ok{color:#047857}',
    '.settings-result.err{color:#dc2626}',
    '#settings-open{position:fixed;top:16px;right:16px;z-index:9998;padding:8px 15px;border-radius:9px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;font-size:14px;font-family:inherit;box-shadow:0 2px 8px rgba(15,23,42,.08)}',
    '#settings-open.needs-setup{background:#fef2f2;border-color:#fecaca;color:#b91c1c;font-weight:600}'
  ].join('');

  var presets = [];
  var providerKeys = {};
  var providerProfiles = {};
  function el(id) { return document.getElementById(id); }

  function setStatus(ready, missing) {
    var box = el('settings-status'), button = el('settings-open');
    if (ready) {
      box.className = 'settings-status ok';
      box.textContent = '模型已配置，可以正常对话。';
      button.classList.remove('needs-setup');
      button.textContent = '设置';
    } else {
      box.className = 'settings-status warn';
      box.textContent = ((missing || []).join('；') || '尚未完成配置') + '。填写后即可使用。';
      button.classList.add('needs-setup');
      button.textContent = '需要配置模型';
    }
  }

  function load() {
    return fetch('/settings').then(function (r) { return r.json(); }).then(function (data) {
      presets = data.presets || [];
      providerKeys = data.settings.provider_keys || {};
      providerProfiles = data.settings.provider_profiles || {};
      var providers = presets.slice();
      Object.keys(providerProfiles).forEach(function (id) {
        if (!providers.some(function (p) { return p.id === id; })) {
          providers.push({ id: id, label: providerProfiles[id].label || id, base_url: providerProfiles[id].base_url, model: providerProfiles[id].model });
        }
      });
      presets = providers;
      el('settings-preset').innerHTML = presets.map(function (p) {
        return '<option value="' + p.id + '">' + p.label + '</option>';
      }).join('');
      el('settings-base-url').value = data.settings.base_url || '';
      el('settings-model').value = data.settings.model_name || '';
      el('settings-key').value = '';
      el('settings-key').placeholder = data.settings.api_key_set
        ? ('已保存 ' + data.settings.api_key + '，留空表示不修改')
        : '请填写 API 密钥';
      el('settings-mineru-key').placeholder = data.settings.mineru_api_key_set
        ? ('已保存 ' + data.settings.mineru_api_key + '，留空表示不修改')
        : '留空则使用主 LLM 密钥';
      el('settings-ocr-model').value = data.settings.ocr_model || 'unlimited-ocr';
      el('settings-voice-short').checked = data.settings.voice_short_reply !== false;
      el('settings-voice-no-think').checked = data.settings.voice_disable_thinking !== false;
      el('settings-dashscope-key').value = '';
      el('settings-dashscope-key').placeholder = data.settings.dashscope_api_key_set
        ? ('已配置 ' + data.settings.dashscope_api_key + '，留空即可')
        : '未配置：可在此填阿里百炼 Key，或在上方模型配置里填';
      el('settings-dashscope-model').value = data.settings.dashscope_realtime_model
        || 'qwen-audio-3.0-realtime-plus';
      el('settings-heartbeat-enabled').checked = data.settings.heartbeat_enabled !== false;
      el('settings-heartbeat-time').value = data.settings.heartbeat_time || '08:00';
      var profile = data.settings.owner_profile || {};
      el('settings-profile-field').value = profile.field || '';
      el('settings-profile-methods').value = profile.methods || '';
      el('settings-profile-notes').value = profile.notes || '';
      el('settings-ocr-key').placeholder = data.settings.ocr_api_key_set
        ? ('已保存 ' + data.settings.ocr_api_key + '，留空表示不修改')
        : '留空则使用主 LLM 密钥';
      var hit = presets.filter(function (p) { return p.base_url === data.settings.base_url; })[0];
      if (!hit && data.settings.model_name) {
        hit = presets.filter(function (p) { return p.model === data.settings.model_name; })[0];
      }
      if (hit) el('settings-preset').value = hit.id;
      var selected = hit || presets[0];
      if (selected) {
        var link = el('settings-api-url');
        link.href = selected.api_url || '#';
        link.style.visibility = selected.api_url ? 'visible' : 'hidden';
        el('settings-key').placeholder = providerKeys[selected.id]
          ? ('已保存 ' + providerKeys[selected.id] + '，留空表示不修改')
          : '请填写 API 密钥';
      }
      setStatus(data.ready, data.missing);
    });
  }

  function qwenStatus() {
    return fetch('/settings/qwen-audio').then(function (r) { return r.json(); }).then(function (d) {
      var status = el('settings-qwen-status');
      if (d.ok) {
        status.textContent = '运行中：' + d.url;
        status.style.color = '#047857';
      } else {
        status.textContent = d.dashscope_key_set ? '未运行' : '未配置 DashScope Key';
        status.style.color = '#64748b';
      }
      return d;
    }).catch(function () {
      var status = el('settings-qwen-status');
      status.textContent = '状态查询失败';
      status.style.color = '#dc2626';
    });
  }

  function body() {
    var selectedProviderId = el('settings-preset').value;
    var selectedProvider = presets.filter(function (p) { return p.id === selectedProviderId; })[0] || {};
    var payload = {
      base_url: el('settings-base-url').value.trim(),
      model_name: el('settings-model').value.trim(),
      tts_enabled: el('settings-tts').checked,
      voice_short_reply: el('settings-voice-short').checked,
      voice_disable_thinking: el('settings-voice-no-think').checked,
      provider_id: selectedProviderId,
      provider_label: selectedProvider.label || selectedProviderId,
      ocr_model: el('settings-ocr-model').value.trim(),
      heartbeat_enabled: el('settings-heartbeat-enabled').checked,
      heartbeat_time: el('settings-heartbeat-time').value || '08:00',
      owner_profile: {
        field: el('settings-profile-field').value.trim(),
        methods: el('settings-profile-methods').value.trim(),
        notes: el('settings-profile-notes').value.trim()
      },
    };
    var key = el('settings-key').value.trim();
    if (key) payload.api_key = key;
    var mineruKey = el('settings-mineru-key').value.trim();
    if (mineruKey) payload.mineru_api_key = mineruKey;
    var ocrKey = el('settings-ocr-key').value.trim();
    if (ocrKey) payload.ocr_api_key = ocrKey;
    var dashscopeKey = el('settings-dashscope-key').value.trim();
    if (dashscopeKey) payload.dashscope_api_key = dashscopeKey;
    payload.dashscope_realtime_model = el('settings-dashscope-model').value.trim()
      || 'qwen-audio-3.0-realtime-plus';
    return payload;
  }

  function result(ok, text) {
    var box = el('settings-result');
    box.className = 'settings-result ' + (ok ? 'ok' : 'err');
    box.textContent = text;
  }

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
    var holder = document.createElement('div');
    holder.innerHTML = PANEL_HTML;
    document.body.appendChild(holder.firstElementChild);
    // 外壳接管后不再需要悬浮按钮，仅保留隐藏节点供状态更新复用
    var open = document.createElement('button');
    open.id = 'settings-open';
    open.style.display = 'none';
    open.setAttribute('aria-hidden', 'true');
    document.body.appendChild(open);

    open.onclick = function () {
      load().then(function () {
        el('settings-result').textContent = '';
        el('settings-modal').classList.add('show');
        qwenStatus();
      });
    };
    el('settings-close').onclick = function () { el('settings-modal').classList.remove('show'); };
    el('settings-modal').onclick = function (e) {
      if (e.target.id === 'settings-modal') el('settings-modal').classList.remove('show');
    };
    el('settings-qwen-start').onclick = function () {
      var button = el('settings-qwen-start');
      var status = el('settings-qwen-status');
      button.disabled = true;
      status.textContent = '启动中…';
      fetch('/settings/qwen-audio/start', { method: 'POST' })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          button.disabled = false;
          status.textContent = res.d.message || (res.ok ? '已启动' : '启动失败');
          status.style.color = res.d.ok ? '#047857' : '#dc2626';
        })
        .catch(function () {
          button.disabled = false;
          status.textContent = '启动请求失败';
          status.style.color = '#dc2626';
        });
    };
    el('settings-dashscope-pull').onclick = function () {
      var button = el('settings-dashscope-pull');
      var status = el('settings-qwen-status');
      var modelInput = el('settings-dashscope-model');
      var listEl = el('settings-dashscope-model-list');
      button.disabled = true;
      status.textContent = '正在拉取 DashScope 模型…';
      status.style.color = '#64748b';
      var key = el('settings-dashscope-key').value.trim();
      var payload = {
        base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        provider_id: 'dashscope'
      };
      if (key) payload.api_key = key;
      fetch('/settings/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      }).then(function (res) {
        if (!res.ok) {
          status.textContent = res.d.detail || '拉取失败';
          status.style.color = '#dc2626';
          return;
        }
        var list = (res.d.models || []).filter(function (m) {
          return m && ['mineru', 'unlimited-ocr', 'qwen3-embedding', 'qwen3-reranker'].indexOf(m) < 0;
        });
        listEl.innerHTML = list.map(function (m) {
          return '<option value="' + m + '">';
        }).join('');
        var selectEl = document.getElementById('settings-dashscope-model-select');
        if (selectEl) {
          selectEl.innerHTML = '<option value="">请选择实时语音模型…</option>' + list.map(function (m) {
            var realtime = m.indexOf('realtime') >= 0;
            return '<option value="' + m + '"' + (realtime ? '' : ' disabled') + '>' + m + (realtime ? '' : '（非实时语音，不可用）') + '</option>';
          }).join('');
          selectEl.style.display = list.length ? 'block' : 'none';
        }
        status.textContent = '拉取到 ' + list.length + ' 个 DashScope 模型，请从下拉框选择。';
        status.style.color = '#047857';
        if (!modelInput.value || modelInput.value === 'qwen-audio-3.0-realtime-plus') {
          var realtime = list.filter(function (m) {
            return m.indexOf('realtime') >= 0;
          })[0];
          if (realtime) modelInput.value = realtime;
        }
      }).catch(function (err) {
        status.textContent = '拉取失败：' + String(err);
        status.style.color = '#dc2626';
      }).then(function () {
        button.disabled = false;
      });
    };
    var dashModelSelect = document.getElementById('settings-dashscope-model-select');
    if (dashModelSelect) {
      dashModelSelect.onchange = function () {
        if (dashModelSelect.value) el('settings-dashscope-model').value = dashModelSelect.value;
      };
    }
    el('settings-preset').onchange = function (e) {
      var p = presets.filter(function (x) { return x.id === e.target.value; })[0];
      if (p) {
        var link = el('settings-api-url');
        link.href = p.api_url || '#';
        link.style.visibility = p.api_url ? 'visible' : 'hidden';
        el('settings-key').value = '';
        el('settings-key').placeholder = providerKeys[p.id]
          ? ('已保存 ' + providerKeys[p.id] + '，留空表示不修改')
          : '请填写 API 密钥';
        if (p.id !== 'custom') {
          el('settings-base-url').value = p.base_url;
          el('settings-model').value = p.model;
        }
      }
    };
    el('settings-model-select').onchange = function (e) {
      if (e.target.value) el('settings-model').value = e.target.value;
    };
    el('settings-fetch-models').onclick = function () {
      var button = el('settings-fetch-models');
      var msg = el('settings-models-msg');
      button.disabled = true;
      msg.textContent = '正在拉取模型列表…';
      var payload = {
        base_url: el('settings-base-url').value.trim(),
        api_key: el('settings-key').value.trim(),
        provider_id: el('settings-preset').value
      };
      fetch('/settings/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) { msg.textContent = res.d.detail || '拉取失败'; return; }
          var list = res.d.models || [];
          list = list.filter(function (m) {
            return ['mineru', 'unlimited-ocr', 'qwen3-embedding', 'qwen3-reranker'].indexOf(m) < 0;
          });
          var catalog = res.d.catalog || [];
          var catalogById = {};
          catalog.forEach(function (c) { catalogById[c.id] = c; });
          el('settings-model-list').innerHTML = list.map(function (m) {
            return '<option value="' + m + '">';
          }).join('');
          var select = el('settings-model-select');
          select.style.display = list.length ? 'block' : 'none';
          select.innerHTML = '<option value="">选择模型…</option>' + list.map(function (m) {
            var meta = catalogById[m] || { label: m, category: '其他', context: '-' };
            return '<option value="' + m + '">' + meta.label + ' · ' + meta.category + ' · ' + meta.context + '</option>';
          }).join('');
          msg.textContent = '已从 ' + el('settings-base-url').value.trim() + ' 拉到 ' + list.length + ' 个模型';
        })
        .catch(function (err) { msg.textContent = String(err); })
        .then(function () { button.disabled = false; });
    };
    el('settings-test').onclick = function () {
      var button = el('settings-test');
      button.disabled = true;
      result(true, '正在测试……');
      fetch('/settings/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body()) })
        .then(function (r) { return r.json(); })
        .then(function (d) { result(d.ok, d.message); })
        .catch(function (err) { result(false, String(err)); })
        .then(function () { button.disabled = false; });
    };
    el('settings-save').onclick = function () {
      var button = el('settings-save');
      button.disabled = true;
      var formPayload = body();
      fetch('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formPayload) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          el('settings-key').value = '';
          setStatus(d.ready, d.missing);
          result(d.ready, d.ready ? d.message : (d.message + '，但仍缺：' + (d.missing || []).join('；')));
          return load();
        })
        .catch(function (err) { result(false, String(err)); })
        .then(function () { button.disabled = false; });
    };
    load().catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
