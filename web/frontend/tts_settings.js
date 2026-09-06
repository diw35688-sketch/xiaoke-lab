// 语音合成设置：和配置对话模型同一种方式——选供应商、填密钥、挑音色、测速度。
(function () {
  var providers = [];

  function el(id) { return document.getElementById(id); }

  var HTML = [
    '<hr style="border:0;border-top:1px solid #e2e8f0;margin:20px 0">',
    '<h3 style="margin:0 0 14px;font-size:16px;color:#0f172a">语音合成</h3>',
    '<label class="settings-field"><span>合成方式</span>',
    '  <div class="preset-row"><select id="tts-provider"></select>',
    '    <a id="tts-api-url" href="#" target="_blank" rel="noopener" class="api-link" style="visibility:hidden">获取 API</a></div>',
    '  <em id="tts-note"></em></label>',
    '<div id="tts-key-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">语音服务密钥</span>',
    '  <input id="tts-key" type="password" placeholder="留空表示不修改" autocomplete="off" />',
    '</div>',
    '<div id="tts-volcano-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">火山引擎密钥（AppID 与 Access Token）</span>',
    '  <div style="display:flex;gap:8px;flex-wrap:wrap">',
    '    <input id="tts-appid" type="text" placeholder="AppID" style="flex:1;min-width:140px" />',
    '    <input id="tts-access-token" type="password" placeholder="Access Token" style="flex:2;min-width:220px" autocomplete="off" />',
    '  </div>',
    '  <em style="display:block;font-style:normal;font-size:12px;color:#64748b;margin-top:5px">旧版小模型填这个；若你是 seed-tts 大模型，请改用下方 AK/SK。</em>',
    '</div>',
    '<div id="tts-ark-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">豆包语音 API Key（一个 Key 直接填）</span>',
    '  <input id="tts-ark-key" type="password" placeholder="粘贴豆包语音控制台的 API Key" autocomplete="off" />',
    '  <em style="display:block;font-style:normal;font-size:12px;color:#64748b;margin-top:5px">官方最简方式：接口里填 x-api-key 即可，不需要 AppID/AK/SK/Endpoint。</em>',
    '</div>',
    '<div id="tts-maas-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">火山方舟 AK/SK（seed-tts 大模型语音合成）</span>',
    '  <div style="display:flex;gap:8px;flex-wrap:wrap">',
    '    <input id="tts-access-key" type="password" placeholder="Access Key ID" style="flex:1;min-width:140px" autocomplete="off" />',
    '    <input id="tts-secret-key" type="password" placeholder="Secret Access Key" style="flex:2;min-width:220px" autocomplete="off" />',
    '  </div>',
    '  <em style="display:block;font-style:normal;font-size:12px;color:#64748b;margin-top:5px">「合成模型」填火山方舟创建的语音 Endpoint ID（ep- 开头），不是 seed-tts 模型名，例如 ep-20240612-xxxxx。</em>',
    '</div>',
    '<div id="tts-model-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">Endpoint ID / 合成模型</span>',
    '  <div class="model-row"><input id="tts-model" type="text" list="tts-model-list" />',
    '    <button id="tts-fetch-models" class="ghost" type="button">拉取模型</button></div>',
    '  <datalist id="tts-model-list"></datalist>',
    '  <select id="tts-model-select" style="display:none;width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:9px;font-size:14px;font-family:inherit;margin-top:8px"></select>',
    '  <em id="tts-models-msg" style="display:block;font-style:normal;font-size:12px;color:#64748b;margin-top:5px"></em>',
    '</div>',
    '<div id="tts-voice-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">音色</span>',
    '  <select id="tts-voice"></select>',
    '</div>',
    '<label class="settings-field"><span>语速 <b id="tts-speed-label">1.0</b>x</span>',
    '  <input id="tts-speed" type="range" min="0.5" max="2" step="0.1" value="1" /></label>',
    '<label class="settings-field settings-inline">',
    '  <input id="tts-enabled" type="checkbox" /><span>自动播报追问与安全提示</span></label>',
    '<label class="settings-field settings-inline">',
    '  <input id="speak-record-ack" type="checkbox" /><span>朗读“已记录”反馈</span></label>',
    '<div class="settings-actions">',
    '  <button id="tts-test" class="ghost">测试合成并计时</button></div>',
    '<p id="tts-result" class="settings-result"></p>'
  ].join('');

  function applyProvider(id) {
    var meta = providers.filter(function (p) { return p.id === id; })[0];
    if (!meta) return;
    el('tts-note').textContent = meta.note || '';
    var apiLink = el('tts-api-url');
    if (apiLink) {
      apiLink.href = meta.api_url || '#';
      apiLink.style.visibility = meta.api_url ? 'visible' : 'hidden';
    }
    var isVolcano = id === 'volcano';
    el('tts-key-row').style.display = (meta.needs_key && !isVolcano) ? 'block' : 'none';
    el('tts-volcano-row').style.display = isVolcano ? 'block' : 'none';
    el('tts-ark-row').style.display = isVolcano ? 'block' : 'none';
    el('tts-maas-row').style.display = isVolcano ? 'block' : 'none';
    el('tts-model-row').style.display = meta.default_model ? 'block' : 'none';
    var voices = meta.voices || [];
    el('tts-voice-row').style.display = voices.length ? 'block' : 'none';
    el('tts-voice').innerHTML = voices.map(function (v) {
      return '<option value="' + v.id + '">' + v.label + '</option>';
    }).join('');
    if (meta.default_model && !el('tts-model').value) el('tts-model').value = meta.default_model;
    var fetchBtn = el('tts-fetch-models');
    if (fetchBtn) {
      if (isVolcano) {
        fetchBtn.textContent = '手动填写 Endpoint ID';
        fetchBtn.disabled = true;
        el('tts-model').placeholder = 'ep-xxxxxxxxxxxxxxxx';
        el('tts-models-msg').textContent = '火山方舟不提供公开模型列表；请在控制台复制语音 Endpoint ID（ep- 开头）填到这里。';
        el('tts-model-list').innerHTML = '';
        el('tts-model-select').style.display = 'none';
      } else {
        fetchBtn.textContent = '拉取模型';
        fetchBtn.disabled = false;
        el('tts-model').placeholder = '';
        el('tts-models-msg').textContent = '';
      }
    }
  }

  function load() {
    return fetch('/tts/providers').then(function (r) { return r.json(); }).then(function (d) {
      providers = d.providers || [];
      el('tts-provider').innerHTML = providers.map(function (p) {
        return '<option value="' + p.id + '">' + p.label + '</option>';
      }).join('');
      var cur = d.current || {};
      el('tts-provider').value = cur.provider || 'browser';
      el('tts-model').value = cur.model || '';
      el('tts-speed').value = cur.speed || 1;
      el('tts-speed-label').textContent = (cur.speed || 1).toFixed ? (cur.speed || 1).toFixed(1) : cur.speed;
      el('tts-enabled').checked = !!cur.enabled;
      el('speak-record-ack').checked = !!cur.speak_record_ack;
      el('tts-key').placeholder = cur.api_key_set ? '已保存，留空表示不修改' : '留空表示不修改';
      el('tts-access-key').placeholder = cur.access_key_set ? '已保存，留空表示不修改' : 'Access Key ID';
      el('tts-secret-key').placeholder = cur.secret_key_set ? '已保存，留空表示不修改' : 'Secret Access Key';
      el('tts-ark-key').placeholder = cur.ark_api_key_set ? '已保存，留空表示不修改' : '粘贴你的专属 API Key';
      applyProvider(el('tts-provider').value);
      if (cur.voice) el('tts-voice').value = cur.voice;
    });
  }

  function payload() {
    var data = {
      tts_provider: el('tts-provider').value,
      tts_model: el('tts-model').value.trim(),
      tts_voice: el('tts-voice').value || '',
      tts_speed: parseFloat(el('tts-speed').value),
      tts_enabled: el('tts-enabled').checked,
      speak_record_ack: el('speak-record-ack').checked
    };
    if (el('tts-provider').value === 'volcano') {
      var appid = el('tts-appid').value.trim();
      var accessToken = el('tts-access-token').value.trim();
      if (appid && accessToken) data.tts_api_key = appid + ':' + accessToken;
      var ak = el('tts-access-key').value.trim();
      var sk = el('tts-secret-key').value.trim();
      if (ak) data.tts_access_key = ak;
      if (sk) data.tts_secret_key = sk;
      var arkKey = el('tts-ark-key').value.trim();
      if (arkKey) data.tts_ark_api_key = arkKey;
    } else {
      var key = el('tts-key').value.trim();
      if (key) data.tts_api_key = key;
    }
    return data;
  }

  function save() {
    return fetch('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload())
    }).then(function (r) { return r.json(); }).then(function (d) {
      // 保存后同步前端朗读开关（对话回答朗读读取它）
      window.ttsEnabled = !!payload().tts_enabled;
      return d;
    });
  }

  function attach() {
    var box = document.querySelector('.settings-box');
    if (!box || document.getElementById('tts-provider')) return;
    var holder = document.createElement('div');
    holder.innerHTML = HTML;
    box.appendChild(holder);

    el('tts-provider').onchange = function (e) { applyProvider(e.target.value); };
    el('tts-speed').oninput = function (e) {
      el('tts-speed-label').textContent = parseFloat(e.target.value).toFixed(1);
    };
    el('tts-fetch-models').onclick = function () {
      var button = el('tts-fetch-models');
      var msg = el('tts-models-msg');
      button.disabled = true;
      msg.textContent = '正在拉取语音模型…';
      var payload = {
        provider: el('tts-provider').value,
        api_key: el('tts-key').value.trim()
      };
      fetch('/tts/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) { msg.textContent = res.d.detail || '拉取失败'; return; }
          var list = res.d.models || [];
          el('tts-model-list').innerHTML = list.map(function (m) {
            return '<option value="' + m + '">';
          }).join('');
          var select = el('tts-model-select');
          select.style.display = list.length ? 'block' : 'none';
          select.innerHTML = '<option value="">选择模型…</option>' + list.map(function (m) {
            return '<option value="' + m + '">' + m + '</option>';
          }).join('');
          msg.textContent = '拉到 ' + list.length + ' 个语音模型';
        })
        .catch(function (err) { msg.textContent = String(err); })
        .then(function () { button.disabled = false; });
    };
    el('tts-model-select').onchange = function (e) {
      if (e.target.value) el('tts-model').value = e.target.value;
    };
    el('tts-test').onclick = function () {
      var button = el('tts-test');
      var out = el('tts-result');
      button.disabled = true;
      out.className = 'settings-result';
      out.textContent = '正在保存并合成测试语音…';
      save().then(function () {
        return fetch('/tts/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
          .then(function (r) { return r.json(); });
      }).then(function (d) {
        out.className = 'settings-result ' + (d.ok ? 'ok' : 'err');
        out.textContent = d.message;
        if (d.ok && el('tts-provider').value !== 'browser' && window.labSpeak) {
          window.labSpeak('语音合成测试，实验记录已保存。');
        } else if (d.ok && window.labSpeak) {
          window.labSpeak('语音合成测试，实验记录已保存。');
        }
      }).catch(function (err) {
        out.className = 'settings-result err';
        out.textContent = String(err);
      }).then(function () { button.disabled = false; });
    };

    // 主保存按钮同时保存语音设置
    var mainSave = el('settings-save');
    if (mainSave && !mainSave.dataset.ttsHooked) {
      mainSave.dataset.ttsHooked = '1';
      mainSave.addEventListener('click', function () { save().catch(function () {}); });
    }
    load().catch(function () {});
  }

  window.__ttsAttach = attach;

  function watch() {
    var opener = document.getElementById('settings-open');
    if (!opener) { setTimeout(watch, 400); return; }
    opener.addEventListener('click', function () { setTimeout(attach, 120); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watch);
  } else {
    watch();
  }
})();
