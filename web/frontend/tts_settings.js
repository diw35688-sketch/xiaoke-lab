// 语音合成设置：和配置对话模型同一种方式——选供应商、填密钥、挑音色、测速度。
(function () {
  var providers = [];

  function el(id) { return document.getElementById(id); }

  var HTML = [
    '<hr style="border:0;border-top:1px solid #e2e8f0;margin:20px 0">',
    '<h3 style="margin:0 0 14px;font-size:16px;color:#0f172a">语音合成</h3>',
    '<label class="settings-field"><span>合成方式</span>',
    '  <select id="tts-provider"></select>',
    '  <em id="tts-note"></em></label>',
    '<div id="tts-key-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">语音服务密钥</span>',
    '  <input id="tts-key" type="password" placeholder="留空表示不修改" autocomplete="off" />',
    '</div>',
    '<div id="tts-url-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">接口地址</span>',
    '  <input id="tts-base-url" type="text" />',
    '</div>',
    '<div id="tts-model-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">合成模型</span>',
    '  <input id="tts-model" type="text" />',
    '</div>',
    '<div id="tts-voice-row" class="settings-field" style="display:none">',
    '  <span style="display:block;font-size:13px;color:#334155;margin-bottom:6px;font-weight:600">音色</span>',
    '  <select id="tts-voice"></select>',
    '</div>',
    '<label class="settings-field"><span>语速 <b id="tts-speed-label">1.0</b>x</span>',
    '  <input id="tts-speed" type="range" min="0.5" max="2" step="0.1" value="1" /></label>',
    '<label class="settings-field settings-inline">',
    '  <input id="tts-enabled" type="checkbox" /><span>自动播报追问与安全提示</span></label>',
    '<div class="settings-actions">',
    '  <button id="tts-test" class="ghost">测试合成并计时</button></div>',
    '<p id="tts-result" class="settings-result"></p>'
  ].join('');

  function applyProvider(id) {
    var meta = providers.filter(function (p) { return p.id === id; })[0];
    if (!meta) return;
    el('tts-note').textContent = meta.note || '';
    el('tts-key-row').style.display = meta.needs_key ? 'block' : 'none';
    el('tts-url-row').style.display = meta.default_base_url ? 'block' : 'none';
    el('tts-model-row').style.display = meta.default_model ? 'block' : 'none';
    var voices = meta.voices || [];
    el('tts-voice-row').style.display = voices.length ? 'block' : 'none';
    el('tts-voice').innerHTML = voices.map(function (v) {
      return '<option value="' + v.id + '">' + v.label + '</option>';
    }).join('');
    if (meta.default_base_url && !el('tts-base-url').value) el('tts-base-url').value = meta.default_base_url;
    if (meta.default_model && !el('tts-model').value) el('tts-model').value = meta.default_model;
  }

  function load() {
    return fetch('/tts/providers').then(function (r) { return r.json(); }).then(function (d) {
      providers = d.providers || [];
      el('tts-provider').innerHTML = providers.map(function (p) {
        return '<option value="' + p.id + '">' + p.label + '</option>';
      }).join('');
      var cur = d.current || {};
      el('tts-provider').value = cur.provider || 'browser';
      el('tts-base-url').value = cur.base_url || '';
      el('tts-model').value = cur.model || '';
      el('tts-speed').value = cur.speed || 1;
      el('tts-speed-label').textContent = (cur.speed || 1).toFixed ? (cur.speed || 1).toFixed(1) : cur.speed;
      el('tts-enabled').checked = !!cur.enabled;
      el('tts-key').placeholder = cur.api_key_set ? '已保存，留空表示不修改' : '留空表示不修改';
      applyProvider(el('tts-provider').value);
      if (cur.voice) el('tts-voice').value = cur.voice;
    });
  }

  function payload() {
    var data = {
      tts_provider: el('tts-provider').value,
      tts_base_url: el('tts-base-url').value.trim(),
      tts_model: el('tts-model').value.trim(),
      tts_voice: el('tts-voice').value || '',
      tts_speed: parseFloat(el('tts-speed').value),
      tts_enabled: el('tts-enabled').checked
    };
    var key = el('tts-key').value.trim();
    if (key) data.tts_api_key = key;
    return data;
  }

  function save() {
    return fetch('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload())
    }).then(function (r) { return r.json(); });
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
