// 服务端语音识别：浏览器采集 PCM，本地编码 16kHz 单声道 WAV，上传给 SenseVoice。
// 相比浏览器自带 Web Speech API：中文实验术语更准，不依赖浏览器厂商云服务。
(function () {
  var CSS = [
    '#asr-bar{flex:0 0 auto;display:flex;align-items:center;gap:9px;background:var(--n-00);border-top:1px solid var(--bd-2);padding:8px 12px;font-size:var(--fs-sm);font-family:inherit}','#asr-btn{border:1px solid var(--bd-2);border-radius:var(--r-md);padding:6px 13px;font-size:var(--fs-sm);cursor:pointer;background:var(--n-00);color:var(--n-800);font-family:inherit}','#asr-btn.rec{background:var(--red-500);border-color:var(--red-500);color:#fff}','#asr-state{color:var(--n-500);font-size:var(--fs-xs);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}','#asr-text{display:none}',
    '#asr-btn{border:0;border-radius:999px;padding:9px 20px;font-size:14px;cursor:pointer;background:#2563eb;color:#fff;font-family:inherit}',
    '#asr-btn.rec{background:#dc2626}',
    '#asr-btn:disabled{opacity:.5;cursor:not-allowed}',
    '#asr-state{color:#64748b;min-width:180px}',
    '#asr-text{color:#0f172a;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'
  ].join('');

  var ctx = null, stream = null, node = null, source = null;
  var chunks = [], recording = false, sampleRate = 16000;

  function el(id) { return document.getElementById(id); }
  function say(text) { el('asr-state').textContent = text; }
  function publishRecordingState(active) {
    document.dispatchEvent(new CustomEvent('lab:recording-state', {
      detail: { recording: active }
    }));
  }

  // 把 Float32 PCM 重采样到 16kHz 并编码为 WAV，服务端可直接读取。
  function encodeWav(samples, inputRate) {
    var ratio = inputRate / sampleRate;
    var length = Math.floor(samples.length / ratio);
    var out = new Int16Array(length);
    for (var i = 0; i < length; i++) {
      var value = samples[Math.floor(i * ratio)];
      value = Math.max(-1, Math.min(1, value));
      out[i] = value < 0 ? value * 0x8000 : value * 0x7fff;
    }
    var buffer = new ArrayBuffer(44 + out.length * 2);
    var view = new DataView(buffer);
    function str(offset, text) {
      for (var j = 0; j < text.length; j++) view.setUint8(offset + j, text.charCodeAt(j));
    }
    str(0, 'RIFF');
    view.setUint32(4, 36 + out.length * 2, true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    str(36, 'data');
    view.setUint32(40, out.length * 2, true);
    for (var k = 0; k < out.length; k++) view.setInt16(44 + k * 2, out[k], true);
    return new Blob([view], { type: 'audio/wav' });
  }

  function start() {
    return navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
      .then(function (media) {
        stream = media;
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        source = ctx.createMediaStreamSource(stream);
        node = ctx.createScriptProcessor(4096, 1, 1);
        chunks = [];
        node.onaudioprocess = function (event) {
          if (!recording) return;
          chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
        };
        source.connect(node);
        node.connect(ctx.destination);
        recording = true;
        publishRecordingState(true);
        say('正在录音，说完点“停止并识别”');
      });
  }

  function stop() {
    recording = false;
    publishRecordingState(false);
    var rate = ctx ? ctx.sampleRate : 48000;
    var total = chunks.reduce(function (sum, c) { return sum + c.length; }, 0);
    var merged = new Float32Array(total);
    var offset = 0;
    chunks.forEach(function (c) { merged.set(c, offset); offset += c.length; });
    try {
      if (node) node.disconnect();
      if (source) source.disconnect();
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
      if (ctx) ctx.close();
    } catch (e) {}
    ctx = null; node = null; source = null; stream = null;
    return encodeWav(merged, rate);
  }

  function upload(blob) {
    var form = new FormData();
    form.append('audio', blob, 'segment.wav');
    return fetch('/asr/transcribe', { method: 'POST', body: form })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); });
  }

  async function streamRecord(text, modeSnapshot, onEvent) {
    var response = await fetch('/record/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transcript: text,
        conversation_id: window.localStorage?.getItem('lab-agent-conversation-id') || null,
        ...modeSnapshot
      })
    });
    if (!response.ok) {
      var failure = await response.json().catch(function () { return {}; });
      throw new Error(failure.detail || '记录请求失败');
    }
    if (!response.body) throw new Error('浏览器不支持流式响应');
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    while (true) {
      var chunk = await reader.read();
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
      var boundary;
      while ((boundary = buffer.indexOf('\n')) >= 0) {
        var line = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 1);
        if (line) onEvent(JSON.parse(line));
      }
      if (chunk.done) break;
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer));
  }
  window.streamExperimentRecord = streamRecord;

  function init() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var bar = document.createElement('div');
    bar.id = 'asr-bar';
    bar.innerHTML = '<button id="asr-btn">开始录音</button>'
      + '<span id="asr-state">本地语音识别（SenseVoice）</span>'
      + '<span id="asr-text"></span>';
    (document.getElementById('sh-chat-main') || document.getElementById('sh-chat') || document.body).appendChild(bar);

    fetch('/asr/status').then(function (r) { return r.json(); }).then(function (d) {
      if (!d.loaded) say('本地识别未加载，首次使用需等待模型加载');
    }).catch(function () {});

    var recordingModeSnapshot = null;
    el('asr-btn').onclick = function () {
      var button = el('asr-btn');
      if (!recording) {
        recordingModeSnapshot = window.interactionModeState.capture('single_recording');
        button.disabled = true;
        start().then(function () {
          button.disabled = false;
          button.textContent = '停止并识别';
          button.classList.add('rec');
        }).catch(function (err) {
          button.disabled = false;
          say('无法访问麦克风：' + err.message);
        });
        return;
      }
      button.disabled = true;
      button.classList.remove('rec');
      button.textContent = '识别中…';
      say('正在识别，首次调用需加载模型，请稍候');
      var blob = stop();
      if (window.turnClient) {
        var unifiedSnapshot = recordingModeSnapshot;
        recordingModeSnapshot = null;
        var requestId = window.turnClient.identity('web-audio');
        var turnId = window.turnClient.identity('turn-audio');
        window.turnClient.submitAudio(blob, {
          modeSnapshot: unifiedSnapshot,
          inputSource: 'single_recording',
          requestId: requestId,
          turnId: turnId,
          filename: 'segment.wav',
          onEvent: function (event) {
            if (event.type === 'turn_status') {
              say(event.text || '正在处理…');
            } else if (event.type === 'turn_result') {
              var committed = event.turn;
              if (!committed) throw new Error('Turn 结果缺少 ConversationTurn');
              window.conversationTurnStore?.acceptCommittedTurn(committed);
              var user = committed.blocks.find(function (block) { return block.type === 'user_text'; });
              var transcript = user && user.payload ? user.payload.text : '';
              el('asr-text').textContent = transcript;
              if (transcript) window.addChatMessage?.(transcript, 'user');
              window.addCommittedAssistantSurface?.(committed);
              say(event.replayed ? '已恢复已提交结果' : '处理完成');
              if (event.business?.kind === 'experiment') {
                window.labStepsReload?.();
                if (window.shellCurrentView?.() === 'records') window.labRecordsReload?.();
              }
            } else if (event.type === 'voice_delivery') {
              window.consumeVoiceDelivery?.(event);
            } else if (event.type === 'turn_error') {
              throw new Error(event.detail || '语音 Turn 失败');
            }
          }
        }).catch(function (err) {
          say('处理失败：' + err.message);
        }).finally(function () {
          button.disabled = false;
          button.textContent = '开始录音';
        });
        return;
      }
      upload(blob).then(function (res) {
        button.disabled = false;
        button.textContent = '开始录音';
        if (!res.ok) {
          say('识别失败：' + (res.data.detail || '未知错误'));
          return;
        }
        var text = res.data.transcript || '';
        el('asr-text').textContent = text;
        if (!text) {
          say('没听清，请再说一次');
          return;
        }
        say('正在连接理解服务…');
        // 统一实验模式；录音走实验记录。
        var submittedModeSnapshot = recordingModeSnapshot || {};
        recordingModeSnapshot = null;
        Promise.resolve(window.beginRecordSurface?.(text, submittedModeSnapshot)).then(function (identity) {
          return streamRecord(text, Object.assign({}, submittedModeSnapshot, identity || {}), function (event) {
          if (event.type === 'record_status') {
            say(event.text || '正在处理…');
            return;
          }
          if (event.type === 'record_error') {
            say('记录失败：' + (event.detail || '未知错误'));
            return;
          }
          if (event.type !== 'record_result') return;
          var d = event.data || {};
          window.publishRecordSurface?.(d);
          // C5-D10：messages 只负责显示；只有 Scheduler 授权事件可以发声。
          (d.voice_delivery_events || []).forEach(function (delivery) {
            window.consumeVoiceDelivery?.(delivery);
          });
          say('已记录');
          if (window.labStepsReload) setTimeout(window.labStepsReload, 800);
          });
        }).catch(function (err) { say('处理失败：' + err.message); });
      }).catch(function (err) {
        button.disabled = false;
        button.textContent = '开始录音';
        say('上传失败：' + err.message);
      });
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
