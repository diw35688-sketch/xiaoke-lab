// 连续通话模式：点一次「通话」后进入电话式交互，不需要每句话都点录音。
//
// 数据流：
//   麦克风常开 → 浏览器本地 VAD 自动切出语音段 → 16kHz WAV 上传 SenseVoice
//   → 转写文本自动送入右侧对话流（/chat/stream）→ 回答自动语音播报
//   → 用户随时说话打断（barge-in），系统继续听下一段。
//
// 与 voice_asr.js 的单次录音不同：这里只点一次开始，之后完全自动。
(() => {
  const $ = id => document.getElementById(id);
  const HINT_SELECTOR = '#cp-hint';

  let active = false;
  let audioCtx = null;
  let stream = null;
  let source = null;
  let processor = null;
  let mute = null;
  let sampleRate = 48000;
  let frameSize = 1024;

  // VAD 状态
  let calibrated = false;
  let calibFrames = 0;
  let calibSum = 0;
  let threshold = 0.008;
  let preFrames = [];
  let preLen = 0;
  let speechFrames = [];
  let speechLen = 0;
  let silenceLen = 0;

  const PRE_SEC = 0.45;        // 保留开口前 0.45s 的预缓冲，避免句首被截断
  const SILENCE_SEC = 0.9;     // 停顿 0.9s 视为一句话结束
  const MIN_SPEECH_SEC = 0.45; // 太短的噪声不送 ASR
  const MAX_SPEECH_SEC = 15;   // 单段上限，超长自动切断
  const SAMPLE_RATE = 16000;   // SenseVoice 固定 16kHz

  let segmentQueue = [];
  let processingQueue = false;
  let autoSpeakWas = false;

  function hint(text) {
    const node = document.querySelector(HINT_SELECTOR);
    if (node) node.textContent = text;
    const status = $('#voice-status');
    if (status) status.textContent = text;
  }

  function setCallButton(on) {
    const button = $('#sh-call');
    if (button) {
      button.textContent = on ? '挂断' : '通话';
      button.classList.toggle('active', on);
    }
    const mic = $('#cp-mic');
    if (mic) {
      mic.textContent = on ? '■' : '◉';
      mic.classList.toggle('rec', on);
    }
  }

  window.phoneCallToggle = () => {
    if (active) stopCall();
    else startCall();
  };

  function setAvatar(state) {
    window.dispatchAvatarState?.(state);
  }

  // 与 voice_asr.js 相同的 16kHz WAV 编码（重采样由线性抽点完成，稳定且零依赖）
  function encodeWav(samples, inputRate) {
    const ratio = inputRate / SAMPLE_RATE;
    const length = Math.floor(samples.length / ratio);
    const out = new Int16Array(length);
    for (let i = 0; i < length; i++) {
      let value = samples[Math.floor(i * ratio)];
      value = Math.max(-1, Math.min(1, value));
      out[i] = value < 0 ? value * 0x8000 : value * 0x7fff;
    }
    const buffer = new ArrayBuffer(44 + out.length * 2);
    const view = new DataView(buffer);
    function str(offset, text) {
      for (let j = 0; j < text.length; j++) view.setUint8(offset + j, text.charCodeAt(j));
    }
    str(0, 'RIFF');
    view.setUint32(4, 36 + out.length * 2, true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, SAMPLE_RATE, true);
    view.setUint32(28, SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    str(36, 'data');
    view.setUint32(40, out.length * 2, true);
    for (let k = 0; k < out.length; k++) view.setInt16(44 + k * 2, out[k], true);
    return new Blob([view], { type: 'audio/wav' });
  }

  function rms(frame) {
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    return Math.sqrt(sum / frame.length);
  }

  function concatFrames(frames) {
    const total = frames.reduce((sum, frame) => sum + frame.length, 0);
    if (!total) return new Float32Array(0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const frame of frames) { merged.set(frame, offset); offset += frame.length; }
    return merged;
  }

  function pushPre(frame) {
    preFrames.push(frame); preLen += frame.length;
    const max = Math.floor(PRE_SEC * sampleRate);
    while (preLen > max && preFrames.length) {
      const removed = preFrames.shift();
      preLen -= removed.length;
    }
  }

  function finalizeSegment() {
    const frames = speechFrames.slice();
    speechFrames = []; speechLen = 0; silenceLen = 0;
    if (!frames.length) return;

    const merged = concatFrames(frames);
    if (merged.length < MIN_SPEECH_SEC * sampleRate) return;

    segmentQueue.push(encodeWav(merged, sampleRate));
    processQueue();
  }

  function handleFrame(frame) {
    if (!active) return;

    // 前 0.5s 只校准环境噪音，不产生语音段。
    if (!calibrated) {
      calibFrames += 1; calibSum += rms(frame);
      if (calibFrames >= 18) {
        const noise = calibSum / calibFrames;
        threshold = Math.max(0.005, Math.min(0.022, noise * 3.5 + 0.002));
        calibrated = true;
        hint('正在听你说话…');
      } else {
        hint('正在校准环境噪音…');
        return;
      }
    }

    const loud = rms(frame) > threshold;
    if (!loud) pushPre(frame);

    if (loud) {
      // 开口瞬间：把预缓冲并入本段，保证句首不丢字。
      if (speechFrames.length === 0) {
          window.stopSpeech?.(); // 用户一开口立即打断正在播放的旧回答（barge-in）
        for (const item of preFrames) { speechFrames.push(item); speechLen += item.length; }
        preFrames = []; preLen = 0;
      }
      speechFrames.push(frame); speechLen += frame.length; silenceLen = 0;

      if (speechLen >= MAX_SPEECH_SEC * sampleRate) finalizeSegment();
    } else if (speechFrames.length > 0) {
      speechFrames.push(frame); speechLen += frame.length; silenceLen += frame.length;
      if (silenceLen >= SILENCE_SEC * sampleRate) finalizeSegment();
    }
  }

  function resetVad() {
    calibrated = false; calibFrames = 0; calibSum = 0; threshold = 0.008;
    preFrames = []; preLen = 0; speechFrames = []; speechLen = 0; silenceLen = 0;
  }

  async function processQueue() {
    if (processingQueue) return;
    processingQueue = true;
    while (active && segmentQueue.length) {
      const blob = segmentQueue.shift();
      try {
        hint('正在识别语音…');
        const form = new FormData();
        form.append('audio', blob, 'phone_segment.wav');
        const response = await fetch('/asr/transcribe', { method: 'POST', body: form });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '识别失败');

        const text = String(data.transcript || '').trim();
        if (!text) { hint('没听清，请再说一次'); continue; }

        hint('转写：' + text);
        setAvatar('thinking');
        // 用户一开口，立刻打断正在播放的旧回答（barge-in）。
        window.stopSpeech?.();

        if (typeof window.composerSend === 'function') {
          window.composerSend(text);
        } else {
          const input = $('#message'), formEl = $('#form');
          if (input && formEl) {
            input.value = text;
            if (typeof formEl.requestSubmit === 'function') formEl.requestSubmit();
            else formEl.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          }
        }

        // 等一小段时间，让聊天流进入 thinking 状态；下一段若此时出现会自然打断。
        await new Promise(resolve => setTimeout(resolve, 350));
      } catch (error) {
        hint('语音识别失败：' + error.message);
        setAvatar('idle');
      }
    }
    processingQueue = false;
  }

  async function startCall() {
    if (active) return;
    const button = $('#sh-call');
    if (button) button.disabled = true;
    const autoSpeak = $('#auto-speak');
    if (autoSpeak) { autoSpeakWas = autoSpeak.checked; autoSpeak.checked = true; }

    try {
      // 先预热 ASR，避免第一句话等模型加载。
      hint('正在准备语音引擎…');
      const warm = await fetch('/asr/warmup', { method: 'POST' });
      if (!warm.ok) throw new Error('ASR 模型加载失败');

      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      sampleRate = audioCtx.sampleRate;
      frameSize = sampleRate >= 32000 ? 1024 : 512;

      source = audioCtx.createMediaStreamSource(stream);
      processor = audioCtx.createScriptProcessor(frameSize, 1, 1);
      mute = audioCtx.createGain();
      mute.gain.value = 0; // 不回放麦克风，避免啸叫；同时保持处理链持续运行

      source.connect(processor);
      processor.connect(mute);
      mute.connect(audioCtx.destination);

      processor.onaudioprocess = event => {
        const frame = event.inputBuffer.getChannelData(0);
        const copy = new Float32Array(frame);
        handleFrame(copy);
      };

      active = true;
      resetVad();
      segmentQueue = [];
      setCallButton(true);
      setAvatar('listening');
      hint('通话已开始，请直接说话');
    } catch (error) {
      active = false;
      setCallButton(false);
      hint('无法开始通话：' + error.message);
      setAvatar('idle');
    } finally {
      if (button) button.disabled = false;
    }
  }

  function stopCall() {
    active = false;
    segmentQueue = [];
    const autoSpeak = $('#auto-speak');
    if (autoSpeak) autoSpeak.checked = autoSpeakWas;
    processingQueue = false;
    try {
      if (processor) { processor.disconnect(); processor.onaudioprocess = null; }
      if (source) source.disconnect();
      if (mute) mute.disconnect();
      if (stream) stream.getTracks().forEach(track => track.stop());
      if (audioCtx) audioCtx.close();
    } catch (_) {}
    processor = null; source = null; mute = null; stream = null; audioCtx = null;
    window.stopSpeech?.();
    setCallButton(false);
    setAvatar('idle');
    hint('通话已结束');
  }

  function bind() {
    const button = $('#sh-call');
    if (!button) return;
    button.onclick = () => {
      if (active) stopCall();
      else startCall();
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }

  // shell.js 重建界面后按钮可能晚到，多等一次。
  document.addEventListener('shell-ready', () => setTimeout(bind, 80));
})();
