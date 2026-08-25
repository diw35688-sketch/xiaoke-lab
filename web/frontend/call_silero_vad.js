// 连续通话模式的 Silero VAD 适配器。
//
// 职责仅限于：加载固定版本运行时、把 vad-web 回调转换为稳定语义事件、
// 返回 16kHz 语音段。麦克风生命周期由 MicVAD 管理；聊天、ASR、TTS 和
// RMS 降级由 phone_call.js 编排。
(function (root) {
  "use strict";

  var VOICE_ASSET_BASE = "/static/vendor/voice/";
  var ORT_URL = VOICE_ASSET_BASE + "ort.min.js";
  var VAD_URL = VOICE_ASSET_BASE + "bundle.min.js";
  var ONNX_BASE = VOICE_ASSET_BASE;
  var PRELOAD_ASSETS = [
    "ort-wasm-simd-threaded.jsep.mjs",
    "ort-wasm-simd-threaded.jsep.wasm",
    "ort-wasm-simd-threaded.mjs",
    "ort-wasm-simd-threaded.wasm",
    "vad.worklet.bundle.min.js",
    "silero_vad_v5.onnx"
  ];
  var POSITIVE_THRESHOLD = 0.3;
  var NEGATIVE_THRESHOLD = 0.25;
  var preloadPromise = null;

  function timings(windowRef) {
    windowRef.__voiceStartupTimings = windowRef.__voiceStartupTimings || {};
    return windowRef.__voiceStartupTimings;
  }

  function progress(windowRef, component, state, detail) {
    windowRef.dispatchEvent?.(new CustomEvent("lab:voice-startup-progress", {
      detail: {component: component, state: state, detail: detail || ""}
    }));
  }

  function loadScript(documentRef, url) {
    return new Promise(function (resolve, reject) {
      var script = documentRef.createElement("script");
      script.src = url;
      script.onload = resolve;
      script.onerror = function () {
        reject(new Error("脚本加载失败：" + url));
      };
      documentRef.head.appendChild(script);
    });
  }

  function ensureRuntime(windowRef, documentRef) {
    var chain = Promise.resolve();
    if (typeof windowRef.ort === "undefined") {
      chain = chain.then(function () { return loadScript(documentRef, ORT_URL); });
    }
    if (!windowRef.vad || !windowRef.vad.MicVAD) {
      chain = chain.then(function () { return loadScript(documentRef, VAD_URL); });
    }
    return chain.then(function () {
      if (!windowRef.vad || !windowRef.vad.MicVAD) {
        throw new Error("Silero VAD 运行时不可用");
      }
    });
  }

  function preloadSileroVad(dependencies) {
    dependencies = dependencies || {};
    var windowRef = dependencies.window || root;
    var documentRef = dependencies.document || windowRef.document;
    if (preloadPromise) return preloadPromise;
    var started = windowRef.performance?.now?.() || Date.now();
    preloadPromise = Promise.all([
      ensureRuntime(windowRef, documentRef),
      ...PRELOAD_ASSETS.map(function (name) {
        return windowRef.fetch(VOICE_ASSET_BASE + name).then(function (response) {
          if (!response.ok) throw new Error("本地语音资源加载失败：" + name);
          return response.arrayBuffer();
        });
      })
    ]).then(function () {
      timings(windowRef).silero_assets_ms = Math.round(
        (windowRef.performance?.now?.() || Date.now()) - started
      );
      progress(windowRef, "silero_assets", "ready");
      return true;
    }).catch(function (error) {
      progress(windowRef, "silero_assets", "error", error.message);
      throw error;
    });
    return preloadPromise;
  }

  async function createCallSileroVad(callbacks, dependencies) {
    callbacks = callbacks || {};
    dependencies = dependencies || {};
    var windowRef = dependencies.window || root;
    var documentRef = dependencies.document || windowRef.document;
    if (!documentRef) throw new Error("Silero VAD 缺少 document 环境");

    await preloadSileroVad({window: windowRef, document: documentRef});
    var initStarted = windowRef.performance?.now?.() || Date.now();

    var segmentActive = false;
    var paused = false;
    var failed = false;

    function emit(type, payload) {
      if (typeof callbacks.onEvent === "function") callbacks.onEvent(type, payload);
    }

    function fail(error) {
      if (failed) return;
      failed = true;
      var normalized = error instanceof Error ? error : new Error(String(error));
      if (typeof callbacks.onFailure === "function") callbacks.onFailure(normalized);
    }

    var instance = await windowRef.vad.MicVAD.new({
      model: "v5",
      baseAssetPath: VOICE_ASSET_BASE,
      onnxWASMBasePath: ONNX_BASE,
      positiveSpeechThreshold: POSITIVE_THRESHOLD,
      negativeSpeechThreshold: NEGATIVE_THRESHOLD,
      redemptionMs: 1500,
      preSpeechPadMs: 450,
      minSpeechMs: 1200,
      onSpeechStart: function () {
        segmentActive = true;
        paused = false;
        emit("speech_started");
      },
      onFrameProcessed: function (probabilities) {
        if (!segmentActive || !probabilities) return;
        var probability = Number(probabilities.isSpeech);
        if (!Number.isFinite(probability)) {
          fail(new Error("Silero VAD 返回了非法人声概率"));
          return;
        }
        if (!paused && probability < NEGATIVE_THRESHOLD) {
          paused = true;
          emit("speech_paused");
        } else if (paused && probability >= POSITIVE_THRESHOLD) {
          paused = false;
          emit("speech_resumed");
        }
      },
      onSpeechEnd: function (audio) {
        if (!segmentActive) return;
        if (!paused) emit("speech_paused");
        segmentActive = false;
        paused = false;
        emit("segment_finalized", audio);
      },
      onVADMisfire: function () {
        segmentActive = false;
        paused = false;
        if (typeof callbacks.onMisfire === "function") callbacks.onMisfire();
      },
      onError: fail,
    });
    timings(windowRef).silero_model_init_ms = Math.round(
      (windowRef.performance?.now?.() || Date.now()) - initStarted
    );

    return {
      start: function () { return instance.start(); },
      stop: function () {
        segmentActive = false;
        paused = false;
        try { instance.pause(); } catch (_) {}
        if (typeof instance.destroy === "function") {
          try { return instance.destroy(); } catch (_) {}
        }
      },
    };
  }

  root.createCallSileroVad = createCallSileroVad;
  root.preloadSileroVad = preloadSileroVad;
  root.preloadVoiceStack = function () {
    var totalStarted = root.performance?.now?.() || Date.now();
    var measuredFetch = function (name, url) {
      var started = root.performance?.now?.() || Date.now();
      return root.fetch(url, {method: "POST"}).then(function (response) {
        if (!response.ok) throw new Error(name + "预热失败");
        return response.json();
      }).then(function (data) {
        timings(root)[name + "_ms"] = Math.round(
          (root.performance?.now?.() || Date.now()) - started
        );
        progress(root, name, "ready");
        return data;
      }).catch(function (error) {
        progress(root, name, "error", error.message);
        throw error;
      });
    };
    progress(root, "voice_stack", "loading");
    var ttsWarmup = root.__ttsWarmupPromise
      ? root.__ttsWarmupPromise.then(function (data) {
          progress(root, "tts_warmup", "ready");
          return data;
        }).catch(function (error) {
          progress(root, "tts_warmup", "error", error.message);
          throw error;
        })
      : measuredFetch("tts_warmup", "/tts/warmup");
    return Promise.allSettled([
      measuredFetch("asr_warmup", "/asr/warmup"),
      preloadSileroVad(),
      ttsWarmup
    ]).then(function (results) {
      timings(root).voice_stack_total_ms = Math.round(
        (root.performance?.now?.() || Date.now()) - totalStarted
      );
      timings(root).ready = results.every(function (item) { return item.status === "fulfilled"; });
      progress(root, "voice_stack", timings(root).ready ? "ready" : "error");
      console.info("[voice-startup]", timings(root));
      return results;
    });
  };
  if (root.document && typeof root.fetch === "function") {
    setTimeout(function () { void root.preloadVoiceStack(); }, 0);
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {createCallSileroVad: createCallSileroVad, preloadSileroVad: preloadSileroVad};
  }
})(typeof window !== "undefined" ? window : globalThis);
