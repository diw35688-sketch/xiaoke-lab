// 连续通话模式：点一次「通话」后进入电话式交互，不需要每句话都点录音。
//
// 数据流：
//   麦克风常开 → 浏览器 Silero VAD 自动切出语音段（失败时回退 RMS）
//   → 16kHz WAV 上传 SenseVoice
//   → 转写文本自动送入右侧对话流（/chat/stream）→ 回答自动语音播报
//   → 用户随时说话打断（barge-in），系统继续听下一段。
//
// 与 voice_asr.js 的单次录音不同：这里只点一次开始，之后完全自动。
(() => {
  const $ = sel => document.querySelector(sel);
  const HINT_SELECTOR = '#cp-hint';
  const CONVERSATION_KEY = 'lab-agent-conversation-id';

  let active = false;
  let voiceMode = 'idle'; // idle | wake | call
  let audioCtx = null;
  let stream = null;
  let source = null;
  let processor = null;
  let mute = null;
  let sileroController = null;
  let sileroPreparePromise = null;
  let captureMode = 'idle';
  let fallbackStarting = false;
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
  const SILENCE_SEC = 1.5;     // 停顿 1.5s 视为一句话结束（原 0.9 会把句中思考停顿误判成句末，加长留思考余量）
  const MIN_SPEECH_SEC = 1.2;  // 太短的噪声（<1.2s）不送 ASR，抗噪音误触（0.6→0.8→1.2 调高）
  const MAX_SPEECH_SEC = 15;   // 单段上限，超长自动切断
  const SAMPLE_RATE = 16000;   // SenseVoice 固定 16kHz

  let segmentQueue = [];
  let processingQueue = false;
  let sessionEndPending = false;
  let autoSpeakWas = false;
  let idleFrames = 0;          // 连续静音帧计数，用于自动重新校准噪音基线
  let runtimeEventChain = Promise.resolve();

  function hint(text) {
    const node = document.querySelector(HINT_SELECTOR);
    if (node) node.textContent = text;
    const status = $('#voice-status');
    if (status) status.textContent = text;
  }

  function setCallButton(on) {
    const mic = $('#cp-mic');
    if (mic) {
      mic.textContent = on ? '■' : '◉';
      mic.classList.toggle('rec', on);
    }
    document.dispatchEvent(new CustomEvent('lab:continuous-call-state', {
      detail: { active: on }
    }));
  }

  window.phoneCallToggle = () => {
    if (active) stopCall();
    else startCall();
  };
  window.phoneCallIsActive = () => active && voiceMode === 'call';
  window.wakeWordToggle = () => {
    if (active) stopCall();
    else startWakeWord();
  };
  window.wakeWordIsWaiting = () => active && voiceMode === 'wake';

  function publishWakeWordState(waiting) {
    document.dispatchEvent(new CustomEvent('lab:wake-word-state', {
      detail: {waiting}
    }));
  }

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

  function enqueueSileroSegment(audio) {
    if (!active || !(audio instanceof Float32Array) || !audio.length) return;
    segmentQueue.push(encodeWav(audio, SAMPLE_RATE));
    processQueue();
  }

  async function reportVoiceRuntimeEvent(type, details = {}) {
    const conversationId = window.localStorage?.getItem(CONVERSATION_KEY);
    if (!conversationId) return;
    try {
      const response = await fetch('/voice/runtime/event', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          conversation_id: conversationId,
          type,
          ...details,
        }),
      });
      if (!response.ok) throw new Error('服务端未接受语音运行事件');
      const data = await response.json();
      for (const delivery of data.voice_delivery_events || []) {
        window.consumeVoiceDelivery?.(delivery);
      }
      return data;
    } catch (error) {
      console.warn(`[voice-runtime] ${type} 上报失败:`, error);
      return null;
    }
  }

  function queueVoiceRuntimeEvent(type, details = {}) {
    runtimeEventChain = runtimeEventChain.then(
      () => reportVoiceRuntimeEvent(type, details),
      () => reportVoiceRuntimeEvent(type, details),
    );
    return runtimeEventChain;
  }

  function handleSileroEvent(type, payload) {
    if (!active) return;
    if (type === 'speech_started' || type === 'speech_resumed') {
      if (type === 'speech_started') void queueVoiceRuntimeEvent('user_speech_started');
      if (type === 'speech_resumed') void queueVoiceRuntimeEvent('user_speech_resumed');
      window.stopSpeech?.();
      setAvatar('listening');
      hint('正在听你说话…');
      return;
    }
    if (type === 'speech_paused') {
      void queueVoiceRuntimeEvent('user_speech_paused');
      hint('检测到短暂停顿，继续等你说完…');
      return;
    }
    if (type === 'segment_finalized') {
      void queueVoiceRuntimeEvent('segment_finalized').then(() => {
        enqueueSileroSegment(payload);
      });
    }
  }

  function handleFrame(frame) {
    if (!active) return;

    // 校准环境噪音基线；校准期间也继续检测语音，避免重校准漏话。
    if (!calibrated) {
      calibFrames += 1; calibSum += rms(frame);
      if (calibFrames >= 18) {
        const noise = calibSum / calibFrames;
        threshold = Math.max(0.02, Math.min(0.06, noise * 6 + 0.01)); // 噪音误触二次调高：下限 0.02、系数 6、上限 0.06
        calibrated = true;
        hint('正在听你说话…');
      } else {
        hint('正在校准环境噪音…');
      }
    }

    const frameRms = rms(frame);
    // 滞后回滞（hysteresis）：未开始语音时需明显高于阈值才触发（抗噪音突刺），
    // 已进入语音后以较低阈值保持（防止句中断音）。
    const loud = frameRms > (speechFrames.length > 0 ? threshold * 0.85 : threshold * 1.8);

    if (!loud) {
      pushPre(frame);
      if (speechFrames.length > 0) {
        speechFrames.push(frame); speechLen += frame.length; silenceLen += frame.length;
        if (silenceLen >= SILENCE_SEC * sampleRate) finalizeSegment();
      } else {
        // 长时间静音后自动重新校准噪音基线（空调/风扇等环境变化时自适应）
        idleFrames += 1;
        if (idleFrames > 64) { // 约 3 秒静音（48k/1024 ≈ 21ms/帧）
          calibFrames = 0; calibSum = 0; calibrated = false;
          idleFrames = 0;
        }
      }
      return;
    }

    idleFrames = 0;
    // 开口瞬间：把预缓冲并入本段，保证句首不丢字。
    if (speechFrames.length === 0) {
        window.stopSpeech?.(); // 用户一开口立即打断正在播放的旧回答（barge-in）
        setAvatar('listening'); // 开口立即切回"正在聆听"（回答播放完会归位 idle）
      for (const item of preFrames) { speechFrames.push(item); speechLen += item.length; }
      preFrames = []; preLen = 0;
    }
    speechFrames.push(frame); speechLen += frame.length; silenceLen = 0;

    if (speechLen >= MAX_SPEECH_SEC * sampleRate) finalizeSegment();
  }

  function resetVad() {
    calibrated = false; calibFrames = 0; calibSum = 0; threshold = 0.008;
    preFrames = []; preLen = 0; speechFrames = []; speechLen = 0; silenceLen = 0;
  }

  async function startRmsCapture() {
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
    mute.gain.value = 0;

    source.connect(processor);
    processor.connect(mute);
    mute.connect(audioCtx.destination);

    processor.onaudioprocess = event => {
      const frame = event.inputBuffer.getChannelData(0);
      handleFrame(new Float32Array(frame));
    };
    resetVad();
    captureMode = 'rms';
  }

  async function switchToRms(error) {
    if (!active || fallbackStarting || captureMode !== 'silero') return;
    fallbackStarting = true;
    captureMode = 'switching';
    try {
      if (sileroController) await sileroController.stop();
    } catch (_) {}
    sileroController = null;
    try {
      await startRmsCapture();
      hint('Silero VAD 不可用，已切换到基础降噪模式：' + error.message);
    } catch (fallbackError) {
      stopCall();
      hint('无法开始通话：Silero 与基础降噪模式均不可用（' + fallbackError.message + '）');
    } finally {
      fallbackStarting = false;
    }
  }

  function prepareSileroCapture() {
    if (sileroController) return Promise.resolve(sileroController);
    if (sileroPreparePromise) return sileroPreparePromise;
    if (typeof window.createCallSileroVad !== 'function') {
      return Promise.reject(new Error('Silero VAD 未加载'));
    }
    const startedAt = window.performance?.now?.() ?? Date.now();
    window.dispatchEvent?.(new CustomEvent('lab:voice-startup-progress', {
      detail: {component: 'microphone', state: 'loading'}
    }));
    sileroPreparePromise = window.createCallSileroVad({
      onEvent: handleSileroEvent,
      onMisfire: () => hint('疑似语音太短，已忽略'),
      onFailure: error => { void switchToRms(error); },
    }).then(controller => {
      sileroController = controller;
      captureMode = 'silero_ready';
      window.__voiceStartupTimings = window.__voiceStartupTimings || {};
      window.__voiceStartupTimings.silero_permission_init_ms = Math.round(
        (window.performance?.now?.() ?? Date.now()) - startedAt
      );
      window.dispatchEvent?.(new CustomEvent('lab:voice-startup-progress', {
        detail: {component: 'microphone', state: 'ready'}
      }));
      return controller;
    }).catch(error => {
      window.dispatchEvent?.(new CustomEvent('lab:voice-startup-progress', {
        detail: {component: 'microphone', state: 'error', detail: error.message}
      }));
      throw error;
    }).finally(() => {
      sileroPreparePromise = null;
    });
    return sileroPreparePromise;
  }
  window.preparePhoneCall = prepareSileroCapture;

  async function startPreferredCapture() {
    if (typeof window.createCallSileroVad !== 'function') {
      await startRmsCapture();
      hint('Silero VAD 未加载，已使用基础降噪模式');
      return;
    }
    try {
      sileroController = await prepareSileroCapture();
      await sileroController.start();
      captureMode = 'silero';
    } catch (error) {
      sileroController = null;
      await startRmsCapture();
      hint('Silero VAD 初始化失败，已使用基础降噪模式：' + error.message);
    }
  }

  async function processQueue() {
    if (processingQueue) return;
    processingQueue = true;
    while (active && segmentQueue.length) {
      const blob = segmentQueue.shift();
      try {
        if (voiceMode === 'wake') {
          hint('正在判断唤醒词…');
          const form = new FormData();
          form.append('audio', blob, 'wake_word.wav');
          const response = await fetch('/asr/transcribe', {method: 'POST', body: form});
          const data = await response.json();
          if (!response.ok) throw new Error(data.detail || '唤醒词识别失败');
          const transcript = String(data.transcript || '').trim();
          const keyword = window.XiaokeWakeWord?.detectWakeWord(transcript);
          if (!keyword) {
            hint(transcript
              ? '识别为“' + transcript.slice(0, 24) + '”，未命中；继续等待“小科小科”'
              : '没有识别出文字，继续等待“小科小科”…');
            setAvatar('idle');
            continue;
          }
          voiceMode = 'call';
          publishWakeWordState(false);
          setCallButton(true);
          setAvatar('listening');
          hint('唤醒成功：' + keyword + '。请直接说话');
          window.dispatchEvent(new CustomEvent('lab:wake-word-detected', {
            detail: {keyword, transcript}
          }));
          continue;
        }
        await queueVoiceRuntimeEvent('asr_processing_started');
        hint('正在识别语音…');
        if (window.turnClient) {
          const modeSnapshot = window.interactionModeState.capture('continuous_call');
          let transcript = '';
          await window.turnClient.submitAudio(blob, {
            modeSnapshot,
            inputSource: 'continuous_call',
            filename: 'phone_segment.wav',
            onEvent: event => {
              if (event.type === 'turn_status') {
                hint(event.text || '正在处理…');
              } else if (event.type === 'turn_result') {
                const committed = event.turn;
                if (!committed) throw new Error('Turn 结果缺少 ConversationTurn');
                window.conversationTurnStore?.acceptCommittedTurn(committed);
                const user = committed.blocks.find(block => block.type === 'user_text');
                transcript = user?.payload?.text || '';
                if (transcript) window.addChatMessage?.(transcript, 'user');
                window.addCommittedAssistantSurface?.(committed);
                hint(transcript ? '转写：' + transcript : '处理完成');
                setAvatar('thinking');
                if (event.business?.session_ended === true && !event.replayed) {
                  sessionEndPending = true;
                  hint('实验记录已结束，正在关闭连续通话…');
                }
              } else if (event.type === 'voice_delivery') {
                window.consumeVoiceDelivery?.(event);
                if (sessionEndPending) stopCall({preservePlayback: true});
              } else if (event.type === 'turn_error') {
                throw new Error(event.detail || '连续通话 Turn 失败');
              } else if (event.type === 'done' && sessionEndPending) {
                stopCall({preservePlayback: true});
              }
            },
          });
          await queueVoiceRuntimeEvent('asr_processing_finished');
          if (!transcript) hint('没听清，请再说一次');
          await new Promise(resolve => setTimeout(resolve, 350));
          continue;
        }
        const form = new FormData();
        form.append('audio', blob, 'phone_segment.wav');
        const response = await fetch('/asr/transcribe', { method: 'POST', body: form });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '识别失败');

        const text = String(data.transcript || '').trim();
        await queueVoiceRuntimeEvent('asr_processing_finished');
        if (!text) { hint('没听清，请再说一次'); continue; }

        hint('转写：' + text);
        setAvatar('thinking');
        // 用户一开口，立刻打断正在播放的旧回答（barge-in）。
        window.stopSpeech?.();

        if (typeof window.composerSend === 'function') {
          window.composerSend(text, {inputSource: 'continuous_call'});
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
        await queueVoiceRuntimeEvent('asr_processing_failed');
        hint('语音识别失败：' + error.message);
        // 通话仍在监听，头像保持聆听等待用户重试
        setAvatar('listening');
      }
    }
    processingQueue = false;
  }

  async function startCall() {
    if (active) return;
    const callStartedAt = window.performance?.now?.() ?? Date.now();
    const button = $('#cp-mic');
    if (button) button.disabled = true;
    const autoSpeak = $('#auto-speak');
    if (autoSpeak) { autoSpeakWas = autoSpeak.checked; autoSpeak.checked = true; }

    try {
      // 只有模型未加载时才提示"正在准备"并预热；已加载直接开始，
      // 避免每次进通话都闪"正在准备语音引擎"误导（预热接口是幂等的，秒回）。
      const statusRes = await fetch('/asr/status');
      const asrStatus = await statusRes.json();
      if (asrStatus && !asrStatus.loaded) {
        hint('首次使用正在加载语音模型，约需 1 分钟…');
        const warm = await fetch('/asr/warmup', { method: 'POST' });
        if (!warm.ok) throw new Error('ASR 模型加载失败');
      }

      active = true;
      voiceMode = 'call';
      segmentQueue = [];
      sessionEndPending = false;
      runtimeEventChain = Promise.resolve();
      await startPreferredCapture();
      window.__voiceStartupTimings = window.__voiceStartupTimings || {};
      window.__voiceStartupTimings.call_click_to_ready_ms = Math.round(
        (window.performance?.now?.() ?? Date.now()) - callStartedAt
      );
      setCallButton(true);
      publishWakeWordState(false);
      setAvatar('listening');
      if (captureMode === 'silero') hint('通话已开始，Silero 正在听你说话');
      console.info('[voice-ready]', window.__voiceStartupTimings);
    } catch (error) {
      active = false;
      voiceMode = 'idle';
      setCallButton(false);
      hint('无法开始通话：' + error.message);
      setAvatar('idle');
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function startWakeWord() {
    if (active) return;
    const button = $('#cp-wake-word');
    if (button) button.disabled = true;
    try {
      const statusRes = await fetch('/asr/status');
      const asrStatus = await statusRes.json();
      if (asrStatus && !asrStatus.loaded) {
        hint('首次使用正在加载语音模型，约需 1 分钟…');
        const warm = await fetch('/asr/warmup', {method: 'POST'});
        if (!warm.ok) throw new Error('ASR 模型加载失败');
      }
      active = true;
      voiceMode = 'wake';
      segmentQueue = [];
      sessionEndPending = false;
      await startPreferredCapture();
      setCallButton(false);
      publishWakeWordState(true);
      setAvatar('idle');
      hint('待机唤醒中，请说“小科小科”');
    } catch (error) {
      active = false;
      voiceMode = 'idle';
      publishWakeWordState(false);
      hint('无法开始唤醒检测：' + error.message);
    } finally {
      if (button) button.disabled = false;
    }
  }

  function stopCall(options = {}) {
    active = false;
    const stoppedMode = voiceMode;
    voiceMode = 'idle';
    captureMode = 'idle';
    segmentQueue = [];
    const autoSpeak = $('#auto-speak');
    if (autoSpeak) autoSpeak.checked = autoSpeakWas;
    processingQueue = false;
    if (sileroController) {
      try { sileroController.stop(); } catch (_) {}
      sileroController = null;
    }
    try {
      if (processor) { processor.disconnect(); processor.onaudioprocess = null; }
      if (source) source.disconnect();
      if (mute) mute.disconnect();
      if (stream) stream.getTracks().forEach(track => track.stop());
      if (audioCtx) audioCtx.close();
    } catch (_) {}
    processor = null; source = null; mute = null; stream = null; audioCtx = null;
    fallbackStarting = false;
    sessionEndPending = false;
    if (!options.preservePlayback) window.stopSpeech?.();
    setCallButton(false);
    publishWakeWordState(false);
    setAvatar('idle');
    hint(stoppedMode === 'wake' ? '待机唤醒已关闭' : '通话已结束');
  }

  function prepareOnPageLoad() {
    if (!navigator.mediaDevices?.getUserMedia) return;
    hint('正在请求麦克风权限并准备人声检测…');
    void prepareSileroCapture().then(() => {
      if (!active) hint('麦克风和人声检测已准备，点击连续通话即可开始');
    }).catch(error => {
      hint('麦克风预准备未完成：' + error.message);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', prepareOnPageLoad, {once: true});
  } else {
    setTimeout(prepareOnPageLoad, 0);
  }

})();
