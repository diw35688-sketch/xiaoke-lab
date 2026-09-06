(() => {
  const PCM_SAMPLE_RATE = 24000;
  const START_LEAD_SECONDS = 0.025;
  let audioContext = null, requestController = null, queue = [], running = false, jobId = 0, currentRuntime = null;
  let activeSources = new Set();
  const status = document.querySelector('#voice-status');
  const now = () => window.performance?.now?.() ?? Date.now();
  const setStatus = text => { if (status) status.textContent = text; };
  const avatar = state => window.dispatchAvatarState?.(state);

  function isCallActive() {
    const btn = document.getElementById('cp-phone-call');
    return !!(btn && btn.classList.contains('active'));
  }
  function settleAvatar() { avatar(isCallActive() ? 'listening' : 'idle'); }
  function cleanForSpeech(text) {
    return String(text || '').replace(/```[\s\S]*?```/g, '代码内容已显示在屏幕上。')
      .replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/[*#>|_~]/g, '').replace(/[μµµ][lL]/g, '微升')
      .replace(/NaOH/g, '氢氧化钠').replace(/KOH/g, '氢氧化钾')
      .replace(/HCl/g, '盐酸').replace(/H2SO4/g, '硫酸')
      .replace(/SDS/g, 'S D S').replace(/EDTA/g, 'E D T A')
      .replace(/DNA/g, 'D N A').replace(/RNA/g, 'R N A')
      .replace(/PCR/g, 'P C R').replace(/Tris/g, 'Tris')
      .replace(/TAE/g, 'T A E').replace(/TE\b/g, 'T E')
      .replace(/PBS/g, 'P B S').replace(/EB\b/g, 'E B')
      .trim();
  }
  function ensureAudioContext() {
    if (!audioContext) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) throw new Error('浏览器不支持 Web Audio 流式播放');
      audioContext = new AudioContextClass();
    }
    if (audioContext.state === 'suspended') return audioContext.resume().then(() => audioContext);
    return Promise.resolve(audioContext);
  }
  function stopActiveSources() {
    for (const source of activeSources) {
      try { source.stop(); } catch (_) {}
      try { source.disconnect(); } catch (_) {}
    }
    activeSources.clear();
  }
  function stopSpeech() {
    jobId += 1; queue = []; requestController?.abort(); requestController = null;
    stopActiveSources(); currentRuntime?.onStopped?.(); currentRuntime = null; settleAvatar();
  }
  function pcm16ToFloat32(bytes, carry) {
    const merged = new Uint8Array(carry.length + bytes.length);
    merged.set(carry, 0); merged.set(bytes, carry.length);
    const usableLength = merged.length - (merged.length % 2);
    const samples = new Float32Array(usableLength / 2);
    const view = new DataView(merged.buffer, merged.byteOffset, usableLength);
    for (let index = 0; index < samples.length; index += 1) samples[index] = view.getInt16(index * 2, true) / 32768;
    return {samples, carry: merged.slice(usableLength)};
  }
  function schedulePcm(context, samples, state, expectedJob, onFirstPlay) {
    if (!samples.length || expectedJob !== jobId) return;
    const buffer = context.createBuffer(1, samples.length, PCM_SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination);
    const startAt = Math.max(context.currentTime + START_LEAD_SECONDS, state.scheduledUntil);
    state.scheduledUntil = startAt + buffer.duration; activeSources.add(source); state.pendingSources += 1;
    source.onended = () => {
      activeSources.delete(source); try { source.disconnect(); } catch (_) {} state.pendingSources -= 1;
      if (state.networkDone && state.pendingSources === 0) state.resolvePlayback();
    };
    source.start(startAt);
    if (!state.firstPlayScheduled) {
      state.firstPlayScheduled = true;
      const delayMs = Math.max(0, (startAt - context.currentTime) * 1000);
      window.setTimeout(() => { if (expectedJob === jobId) onFirstPlay(now()); }, delayMs);
    }
  }
  async function streamAndPlay(text, runtime, expectedJob) {
    const context = await ensureAudioContext();
    const requestStartedAt = now(); requestController = new AbortController(); setStatus('正在接收流式语音…');
    const response = await fetch('/tts/stream', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, speed: runtime?.speechRate ?? 1.0}), signal: requestController.signal,
    });
    const responseHeadersAt = now();
    if (!response.ok || !response.body) {
      let detail = '流式语音请求失败';
      try { const error = await response.json(); if (error?.detail) detail = error.detail; } catch (_) {}
      throw new Error(detail);
    }
    const format = response.headers?.get?.('X-Audio-Format');
    const sampleRate = Number(response.headers?.get?.('X-Audio-Sample-Rate') || PCM_SAMPLE_RATE);
    if (format && format !== 'pcm_s16le') throw new Error(`不支持的流式音频格式：${format}`);
    if (sampleRate !== PCM_SAMPLE_RATE) throw new Error(`不支持的PCM采样率：${sampleRate}`);

    let resolvePlayback;
    const playbackFinished = new Promise(resolve => { resolvePlayback = resolve; });
    const state = {scheduledUntil: context.currentTime, pendingSources: 0, networkDone: false, firstPlayScheduled: false, resolvePlayback};
    const reader = response.body.getReader(); let carry = new Uint8Array(0), firstAudioChunkAt = null, totalBytes = 0;
    try {
      while (expectedJob === jobId) {
        const {value, done} = await reader.read(); if (done) break; if (!value?.byteLength) continue;
        if (firstAudioChunkAt === null) firstAudioChunkAt = now(); totalBytes += value.byteLength;
        const decoded = pcm16ToFloat32(value, carry); carry = decoded.carry;
        schedulePcm(context, decoded.samples, state, expectedJob, startedAt => {
          runtime?.onStarted?.(); setStatus('正在朗读回复…'); avatar('speaking');
          const timing = {
            intent_id: runtime?.timing?.intentId || null, chars: text.length, audio_bytes_at_start: totalBytes,
            turn_to_play_ms: runtime?.timing?.turnStartedAt == null ? null : Math.round(startedAt - runtime.timing.turnStartedAt),
            screen_to_delivery_ms: runtime?.timing?.screenPublishedAt == null ? null : Math.round(runtime.timing.deliveryReceivedAt - runtime.timing.screenPublishedAt),
            delivery_to_request_ms: runtime?.timing?.deliveryReceivedAt == null ? null : Math.round(requestStartedAt - runtime.timing.deliveryReceivedAt),
            response_headers_ms: Math.round(responseHeadersAt - requestStartedAt),
            first_audio_chunk_ms: firstAudioChunkAt == null ? null : Math.round(firstAudioChunkAt - requestStartedAt),
            first_chunk_to_play_ms: firstAudioChunkAt == null ? null : Math.round(startedAt - firstAudioChunkAt),
            delivery_to_play_ms: runtime?.timing?.deliveryReceivedAt == null ? null : Math.round(startedAt - runtime.timing.deliveryReceivedAt),
          };
          window.__voiceTimingSamples = window.__voiceTimingSamples || []; window.__voiceTimingSamples.push(timing);
          console.info('[voice-stream-timing]', timing);
        });
      }
    } finally {
      state.networkDone = true; if (state.pendingSources === 0) state.resolvePlayback();
      try { reader.releaseLock(); } catch (_) {}
    }
    if (expectedJob !== jobId) return;
    if (firstAudioChunkAt === null) throw new Error('流式接口没有返回音频');
    if (carry.length) console.warn('[voice-stream] 忽略末尾不完整的1字节PCM数据');
    await playbackFinished;
  }
  async function processQueue(expectedJob) {
    if (running) return; running = true;
    try {
      while (queue.length && expectedJob === jobId) {
        const item = queue.shift(), runtime = item.runtime || null; currentRuntime = runtime;
        try {
          await streamAndPlay(item.text, runtime, expectedJob);
          if (expectedJob === jobId) runtime?.onFinished?.();
        } catch (error) {
          if (error.name === 'AbortError' || expectedJob !== jobId) break;
          runtime?.onFailed?.(error.message); setStatus('流式语音失败：' + error.message);
        }
        if (currentRuntime === runtime) currentRuntime = null;
      }
      if (expectedJob === jobId) { setStatus(isCallActive() ? '正在聆听，请说话' : '朗读完成'); settleAvatar(); }
    } finally {
      running = false; requestController = null; if (queue.length) processQueue(jobId);
    }
  }
  function addToQueue(text, replace, runtime) {
    if (window.ttsMuted === true) return; if (replace) stopSpeech();
    const clean = cleanForSpeech(text); if (!clean) return; const expectedJob = jobId;
    queue.push({text: clean, runtime}); processQueue(expectedJob);
  }
  window.stopSpeech = stopSpeech;
  window.speak = (text, runtime) => addToQueue(text, true, runtime);
  window.enqueueSpeech = (text, runtime) => addToQueue(text, false, runtime);
  // 页面加载即预连接唯一的火山流式通道，把握手时间藏在用户输入之前。
  const ttsWarmupStartedAt = window.performance?.now?.() ?? Date.now();
  window.__ttsWarmupPromise = fetch('/tts/warmup', {method: 'POST'})
    .then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      window.__voiceStartupTimings = window.__voiceStartupTimings || {};
      window.__voiceStartupTimings.tts_warmup_ms = Math.round(
        (window.performance?.now?.() ?? Date.now()) - ttsWarmupStartedAt
      );
      return true;
    })
    .catch(error => {
      console.warn('[voice-stream] 预连接失败，首轮播放时将自动重连：', error);
      return false;
    });
})();
