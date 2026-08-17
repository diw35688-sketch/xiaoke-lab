// VAD 自动模式：浏览器端 WASM Silero VAD，免按键"开口即录、安静自动识别"。
//
// 与手动模式互斥（同一时刻只有一个录音源）：
//  - composer.js 的 #cp-mic（触发 voice_asr.js 的手动录音）
//  - index.html 的 #mic（浏览器原生语音，已被 composer 隐藏）
// 运行时（onnxruntime-web + vad-web，约 23MB）在用户点开关时才动态加载，
// 不拖慢主页；CDN 加载失败或初始化失败时自动回退，提示使用手动录音。
//
// 按钮位置：主页面放在 composer 输入卡片的控制行（#cp-mic 旁边）；
// 若页面没有 composer（如独立诊断页），则回退为自建底部条。
(function () {
  "use strict";

  var ORT_URL = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/ort.min.js";
  var VAD_URL = "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.22/dist/bundle.min.js";
  // 与 ORT_URL 版本对齐：vad-web 默认指向 1.14.0，但 1.14.0 缺 ort 需要的 .jsep.mjs。
  var ONNX_BASE = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.19.2/dist/";

  var btn = null;
  var myVad = null;
  var active = false;
  var busy = false; // 正在提交识别，防重入

  function el(id) { return document.getElementById(id); }

  function say(text) {
    var status = el("vad-state");
    if (status) status.textContent = text;
  }

  // vad-web 输出的 audio 是 16kHz Float32Array，直接编码为 WAV（无重采样）。
  function encodeWav16k(samples) {
    var length = samples.length;
    var out = new Int16Array(length);
    for (var i = 0; i < length; i++) {
      var value = Math.max(-1, Math.min(1, samples[i]));
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
    view.setUint32(24, 16000, true);
    view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    str(36, "data");
    view.setUint32(40, out.length * 2, true);
    for (var k = 0; k < out.length; k++) view.setInt16(44 + k * 2, out[k], true);
    return new Blob([view], { type: "audio/wav" });
  }

  // 识别结果进聊天框并提交——与 composer.send() 的路径一致：
  // 先塞进隐藏的 #message，再提交隐藏的 #form，由原有事件链处理。
  function submitTranscript(text) {
    var input = document.querySelector("#message");
    var form = document.querySelector("#form");
    if (input && form) {
      input.value = text;
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
      return true;
    }
    return false;
  }

  function upload(audio) {
    var form = new FormData();
    form.append("audio", encodeWav16k(audio), "segment.wav");
    return fetch("/asr/transcribe", { method: "POST", body: form })
      .then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, data: d }; });
      });
  }

  function onSpeechEnd(audio) {
    if (busy) return; // 上一句还在识别时，忽略新结尾
    busy = true;
    say("识别中…");
    upload(audio)
      .then(function (res) {
        busy = false;
        if (!res.ok) {
          var detail = res.data.detail || "未知错误";
          if (detail.indexOf("模型") >= 0) {
            say("识别服务暂不可用（SenseVoice 模型未安装），请用文字或手动录音");
          } else {
            say("识别失败：" + detail);
          }
          return;
        }
        var text = res.data.transcript || "";
        if (!submitTranscript(text)) say("已转写（未找到聊天框）");
      })
      .catch(function (err) {
        busy = false;
        say("上传失败：" + err.message);
      });
  }

  function loadScript(url) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = url;
      s.onload = resolve;
      s.onerror = function () { reject(new Error("脚本加载失败：" + url)); };
      document.head.appendChild(s);
    });
  }

  function loadRuntime() {
    var chain = Promise.resolve();
    if (typeof window.ort === "undefined") chain = chain.then(function () { return loadScript(ORT_URL); });
    if (typeof window.vad === "undefined" || !window.vad.MicVAD) {
      chain = chain.then(function () { return loadScript(VAD_URL); });
    }
    return chain;
  }

  function setButtonsLocked(locked) {
    var asrBtn = el("asr-btn");
    if (asrBtn) asrBtn.disabled = locked;
    var mic = el("mic");
    if (mic) mic.disabled = locked;
    var cpMic = el("cp-mic");
    if (cpMic) cpMic.disabled = locked;
  }

  function isManualRecording() {
    var cpMic = el("cp-mic");
    if (cpMic && cpMic.classList.contains("rec")) return true;
    var asrBtn = el("asr-btn");
    if (asrBtn && asrBtn.textContent.indexOf("停止") >= 0) return true;
    return false;
  }

  function disable() {
    if (myVad) {
      try { myVad.pause(); } catch (e) { /* ignore */ }
      myVad = null;
    }
    active = false;
    if (btn) {
      btn.textContent = "🎤 自动";
      btn.classList.remove("active");
    }
    setButtonsLocked(false);
    say("自动语音已关闭");
  }

  function enable() {
    if (isManualRecording()) {
      say("请先结束手动录音，再开启自动模式");
      return;
    }
    if (btn) { btn.disabled = true; btn.textContent = "加载中…"; }
    loadRuntime()
      .then(function () {
        return window.vad.MicVAD.new({
          model: "v5",
          onnxWASMBasePath: ONNX_BASE,
          onSpeechStart: function () { say("正在听…"); },
          onSpeechEnd: onSpeechEnd,
          onVADMisfire: function () { say("疑似语音太短，已忽略"); },
          onError: function (error) {
            say("VAD 错误：" + (error && error.message ? error.message : String(error)));
          },
        });
      })
      .then(function (vad) {
        myVad = vad;
        vad.start();
        active = true;
        if (btn) {
          btn.disabled = false;
          btn.textContent = "关闭自动";
          btn.classList.add("active");
        }
        setButtonsLocked(true);
        say("自动语音：开口即录，安静后自动识别");
      })
      .catch(function (err) {
        if (btn) { btn.disabled = false; btn.textContent = "🎤 自动"; }
        say("自动语音不可用：" + (err && err.message ? err.message : String(err)) + "。请使用手动录音");
      });
  }

  function init() {
    // 主页面：composer 输入卡片（#cp-card）的控制行，麦克风按钮（#cp-mic）旁边。
    var cpLeft = document.querySelector("#cp-row .cp-left");
    if (cpLeft) {
      var style = document.createElement("style");
      style.textContent =
        "#vad-mode-btn.active{background:var(--brand,#3158c8);border-color:var(--brand,#3158c8);color:#fff}";
      document.head.appendChild(style);

      btn = document.createElement("button");
      btn.id = "vad-mode-btn";
      btn.type = "button";
      btn.className = "cp-chip";
      btn.textContent = "🎤 自动";
      btn.title = "自动语音：开口即录，安静后自动识别（免按键）";
      btn.addEventListener("click", function () {
        if (active) disable();
        else enable();
      });
      var cpMic = el("cp-mic");
      if (cpMic && cpMic.parentNode) cpMic.parentNode.insertBefore(btn, cpMic.nextSibling);
      else cpLeft.appendChild(btn);

      // 状态文字：放在 composer 的 #cp-wrap 里（#cp-meta 之后，
      // composer 的 renderMeta 只重写 #cp-meta 自身，不会冲掉本元素）。
      var state = document.createElement("span");
      state.id = "vad-state";
      state.style.cssText =
        "display:block;padding:4px 16px 2px;font-size:var(--fs-xs,#12px);color:var(--n-500,#64748b);line-height:1.6";
      state.textContent = "🎤 自动语音：开口即录，安静自动识别";
      var wrap = document.getElementById("cp-wrap");
      if (wrap) wrap.appendChild(state);
      return;
    }

    // 兜底（页面没有 composer，如独立诊断页）：自建一条底部语音条。
    var bar = document.createElement("div");
    bar.id = "vad-bar";
    bar.style.cssText =
      "flex:0 0 auto;display:flex;align-items:center;gap:9px;padding:8px 12px;" +
      "border-top:1px solid #e2e8f0;background:#f8fafc;font-size:13px;font-family:inherit";
    btn = document.createElement("button");
    btn.id = "vad-mode-btn";
    btn.textContent = "🎤 自动";
    btn.style.cssText =
      "border:1px solid #cfdaff;border-radius:999px;padding:6px 14px;font-size:13px;" +
      "cursor:pointer;background:#eef3ff;color:#3158c8;font-family:inherit";
    btn.addEventListener("click", function () {
      if (active) disable();
      else enable();
    });
    var state = document.createElement("span");
    state.id = "vad-state";
    state.style.cssText = "color:#64748b;font-size:12px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";
    state.textContent = "🎤 自动语音：开口即录，安静自动识别（首次需下载 WASM 运行时）";
    bar.appendChild(btn);
    bar.appendChild(state);
    var asrBar = el("asr-bar");
    if (asrBar && asrBar.parentNode) asrBar.parentNode.insertBefore(bar, asrBar.nextSibling);
    else document.body.appendChild(bar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(init, 150); });
  } else {
    setTimeout(init, 150);
  }
})();
