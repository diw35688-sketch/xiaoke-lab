// 模型设置面板：任何人都能在浏览器里配置模型，不需要碰服务器文件。
(function () {
  var PANEL_HTML = [
    '<div id="settings-modal" class="settings-mask">',
    '  <div class="settings-box">',
    '    <header class="settings-head"><h2>模型与语音服务</h2>',
    '      <button id="settings-close" title="close">x</button></header>',
    '    <div id="settings-status" class="settings-status"></div>',
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
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">文档解析（MinerU / OCR）</div>',
    '    <label class="settings-field"><span>MinerU 文件解析地址</span>',
    '      <input id="settings-mineru-url" type="text" placeholder="https://api.llm.ustc.edu.cn/mineru/file_parse" /></label>',
    '    <label class="settings-field"><span>MinerU 密钥</span>',
    '      <input id="settings-mineru-key" type="password" autocomplete="off" placeholder="留空则使用主 LLM 密钥" /></label>',
    '    <label class="settings-field"><span>图片 OCR 地址</span>',
    '      <input id="settings-ocr-url" type="text" placeholder="https://api.llm.ustc.edu.cn/v1" /></label>',
    '    <label class="settings-field"><span>图片 OCR 模型</span>',
    '      <input id="settings-ocr-model" type="text" placeholder="unlimited-ocr" /></label>',
    '    <label class="settings-field"><span>图片 OCR 密钥</span>',
    '      <input id="settings-ocr-key" type="password" autocomplete="off" placeholder="留空则使用主 LLM 密钥" /></label>',
    '    <div style="font-size:13px;font-weight:700;color:#0f172a;margin:18px 0 10px">社区设置</div>',
    '    <label class="settings-field"><span>远程社区服务地址</span>',
    '      <input id="settings-community-url" type="text" placeholder="http://124.221.234.222:3000/api" /></label>',
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
    '.settings-field input,.settings-field select{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:9px;font-size:14px;font-family:inherit}',
    '.settings-field em{display:block;font-style:normal;font-size:12px;color:#94a3b8;margin-top:5px}',
    '.settings-inline{display:flex;align-items:center;gap:9px}',
    '.settings-inline span{font-weight:400;font-size:13px;color:#334155;margin:0}',
    '.settings-inline input{width:auto}',
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
      el('settings-key').placeholder = data.settings.api_key_set
        ? ('已保存 ' + data.settings.api_key + '，留空表示不修改')
        : '请填写 API 密钥';
      el('settings-mineru-url').value = data.settings.mineru_file_parse_url || '';
      el('settings-mineru-key').placeholder = data.settings.mineru_api_key_set
        ? ('已保存 ' + data.settings.mineru_api_key + '，留空表示不修改')
        : '留空则使用主 LLM 密钥';
      el('settings-ocr-url').value = data.settings.ocr_base_url || '';
      el('settings-ocr-model').value = data.settings.ocr_model || 'unlimited-ocr';
      el('settings-voice-short').checked = data.settings.voice_short_reply !== false;
      el('settings-voice-no-think').checked = data.settings.voice_disable_thinking !== false;
      el('settings-community-url').value = data.settings.community_base_url || 'http://124.221.234.222:3000/api';
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
      mineru_file_parse_url: el('settings-mineru-url').value.trim(),
      ocr_base_url: el('settings-ocr-url').value.trim(),
      ocr_model: el('settings-ocr-model').value.trim(),
      community_base_url: el('settings-community-url').value.trim() || 'http://124.221.234.222:3000/api'
    };
    var key = el('settings-key').value.trim();
    if (key) payload.api_key = key;
    var mineruKey = el('settings-mineru-key').value.trim();
    if (mineruKey) payload.mineru_api_key = mineruKey;
    var ocrKey = el('settings-ocr-key').value.trim();
    if (ocrKey) payload.ocr_api_key = ocrKey;
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
      });
    };
    el('settings-close').onclick = function () { el('settings-modal').classList.remove('show'); };
    el('settings-modal').onclick = function (e) {
      if (e.target.id === 'settings-modal') el('settings-modal').classList.remove('show');
    };
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
