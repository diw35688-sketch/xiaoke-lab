// 手机演示页逻辑：点击录音 → 16kHz WAV → /asr/transcribe → /record 结构化 → 播报追问。
// 与 voice_asr.js 同一套接口约定；页面独立，不依赖桌面版 composer/shell。
(function () {
  "use strict";

  // 手机演示页没有桌面端 auto-speak 控件，默认沿用原有“可播报”体验。
  window.ttsEnabled = window.ttsMuted !== true;

  var btn = document.getElementById("m-record-btn");
  var logEl = document.getElementById("m-log");
  var emptyEl = document.getElementById("m-empty");
  var statusEl = document.getElementById("m-status");
  var hintEl = document.getElementById("m-hint");

  var ctx = null, stream = null, source = null, node = null;
  var chunks = [];
  var recording = false;
  var busy = false;
  var TARGET_RATE = 16000;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setHint(text) {
    if (hintEl) hintEl.textContent = text;
  }

  function addBubble(text, cls, tag, sub) {
    if (emptyEl) { emptyEl.remove(); emptyEl = null; }
    var row = document.createElement("div");
    row.className = "bubble" + (cls ? " " + cls : "");
    if (tag) {
      var tagEl = document.createElement("span");
      tagEl.className = "tag";
      tagEl.textContent = tag;
      row.appendChild(tagEl);
    }
    var body = document.createElement("span");
    body.textContent = text;
    row.appendChild(body);
    if (sub) {
      var subEl = document.createElement("span");
      subEl.className = "sub";
      subEl.textContent = sub;
      row.appendChild(subEl);
    }
    logEl.appendChild(row);
    logEl.scrollTop = logEl.scrollHeight;
    return row;
  }

  // 播报已收敛到 local_tts.js 的 window.speak（单一发声源，含队列 + 打断 + 浏览器兜底）。

  // Float32 → 16kHz 单声道 PCM WAV（与 voice_asr.js 相同的零依赖编码）。
  function encodeWav(samples, inputRate) {
    var ratio = inputRate / TARGET_RATE;
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
    str(0, "RIFF");
    view.setUint32(4, 36 + out.length * 2, true);
    str(8, "WAVE");
    str(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, TARGET_RATE, true);
    view.setUint32(28, TARGET_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    str(36, "data");
    view.setUint32(40, out.length * 2, true);
    for (var k = 0; k < out.length; k++) view.setInt16(44 + k * 2, out[k], true);
    return new Blob([view], { type: "audio/wav" });
  }

  function startRecording() {
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
      });
  }

  function stopRecording() {
    recording = false;
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
    } catch (e) { /* 忽略清理异常 */ }
    ctx = null; node = null; source = null; stream = null;
    return encodeWav(merged, rate);
  }

  function postAsr(blob) {
    var form = new FormData();
    form.append("audio", blob, "segment.wav");
    return fetch("/asr/transcribe", { method: "POST", body: form })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); });
  }

  async function postRecord(text, onEvent) {
    var response = await fetch("/record/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: text })
    });
    if (!response.ok) {
      var failure = await response.json().catch(function () { return {}; });
      throw new Error(failure.detail || "记录请求失败");
    }
    if (!response.body) throw new Error("浏览器不支持流式响应");
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    while (true) {
      var chunk = await reader.read();
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
      var boundary;
      while ((boundary = buffer.indexOf("\n")) >= 0) {
        var line = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 1);
        if (line) onEvent(JSON.parse(line));
      }
      if (chunk.done) break;
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer));
  }

  function handleRecordResult(d) {
    var degraded = d.extraction && d.extraction.degraded;

    var entityText = Object.keys(d.entities || {}).length
      ? Object.keys(d.entities).map(function (k) {
          return k + "：" + d.entities[k];
        }).join("，")
      : "";

    addBubble(d.transcript, "user", "我的口述");
    if (entityText) addBubble("已结构化：\n" + entityText, null, "系统");
    else if (degraded) addBubble("已按原文保存（结构化暂不可用）", "warn", "系统");
    else addBubble("已保存口述。", null, "系统");

    // B4：渲染 messages（前端只按 kind/screen_target 上样式，不判断内容；话术来自后端）
    var msgs = d.messages || [];
    msgs.forEach(function (m) {
      var isAsk = m.kind === "clarification" || m.screen_target === "current_question";
      addBubble(m.text, isAsk ? null : "warn", isAsk ? "小科追问" : "系统");
    });
    // C5-D10：屏幕 messages 本身没有播放权，只消费 Scheduler 授权事件。
    (d.voice_delivery_events || []).forEach(function (event) {
      window.consumeVoiceDelivery?.(event);
    });
  }

  function fail(text) {
    addBubble(text, "warn", "出错了");
    setStatus("出错了");
  }

  btn.addEventListener("click", function () {
    if (busy) return;
    if (!recording) {
      btn.disabled = true;
      setStatus("请求麦克风…");
      startRecording().then(function () {
        btn.disabled = false;
        btn.classList.add("rec");
        btn.textContent = "■";
        setStatus("正在录音，说完再点一次");
        setHint("录音中…");
      }).catch(function (err) {
        btn.disabled = false;
        fail("无法访问麦克风：" + (err && err.message ? err.message : err));
      });
      return;
    }

    busy = true;
    btn.disabled = true;
    btn.classList.remove("rec");
    btn.textContent = "…";
    setStatus("识别中…");
    setHint("正在识别，请稍候");

    var blob = stopRecording();
    postAsr(blob).then(function (res) {
      if (!res.ok) {
        var detail = res.data.detail || "未知错误";
        busy = false;
        btn.disabled = false;
        btn.textContent = "🎤";
        fail("识别失败：" + detail);
        return;
      }
      var text = res.data.transcript || "";
      if (!text) {
        busy = false;
        btn.disabled = false;
        btn.textContent = "🎤";
        fail("没有识别到内容，请再试一次");
        return;
      }
      addBubble(text, null, "识别结果");
      setStatus("正在连接理解服务…");
      return postRecord(text, function (event) {
        if (event.type === "record_status") {
          setStatus(event.text || "正在处理…");
          return;
        }
        if (event.type === "record_error") throw new Error(event.detail || "记录失败");
        if (event.type === "record_result") handleRecordResult(event.data || {});
      });
    }).then(function () {
      busy = false;
      btn.disabled = false;
      btn.textContent = "🎤";
      setStatus("已记录");
      setHint("点击开始录音，说完再点一次");
    }).catch(function (err) {
      busy = false;
      btn.disabled = false;
      btn.textContent = "🎤";
      fail("处理失败：" + (err && err.message ? err.message : err));
    });
  });
})();
