// Frontend boundary for backend-owned voice playback authorization.
// CONTENT_ELIGIBLE is only a content candidate; only READY/PREEMPT may reach TTS.
(() => {
  const CONVERSATION_KEY = 'lab-agent-conversation-id';
  const now = () => window.performance?.now?.() ?? Date.now();

  // ── TTS 回声保护 ──
  // voice_delivery_client.js 是 __ttsSpeaking 标志的唯一管理者。
  // phone_call.js / vad_mode.js / realtime_voice_inline.js 只读取它。
  // 多条语音项排队时用计数器确保全部播完才解除静音。
  let activeTTSCount = 0;
  let ttsIdleTimer = null;

  function ttsStarted() {
    if (ttsIdleTimer) { clearTimeout(ttsIdleTimer); ttsIdleTimer = null; }
    activeTTSCount++;
    window.__ttsSpeaking = true;
    window.__vadMuteForTTS?.();
  }

  function ttsFinished() {
    activeTTSCount = Math.max(0, activeTTSCount - 1);
    window.__lastTTSFinishedAt = Date.now();
    if (activeTTSCount === 0 && !ttsIdleTimer) {
      ttsIdleTimer = setTimeout(() => {
        ttsIdleTimer = null;
        window.__ttsSpeaking = false;
        window.__vadUnmuteAfterTTS?.();
      }, 700);
    }
  }

  async function reportTtsEvent(type, item, error) {
    const conversationId = window.localStorage?.getItem(CONVERSATION_KEY);
    if (!conversationId) return;
    try {
      const response = await fetch('/voice/runtime/event', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          conversation_id: conversationId,
          type,
          intent_id: item.intent_id,
          priority: item.priority,
          ...(error ? {error} : {}),
        }),
      });
      if (!response.ok) throw new Error('服务端未接受 TTS 事件');
      const data = await response.json();
      for (const delivery of data.voice_delivery_events || []) {
        consumeVoiceDelivery(delivery);
      }
    } catch (error_) {
      console.warn(`[voice-runtime] ${type} 上报失败:`, error_);
    }
  }

  function runtimeHooks(item, deliveryReceivedAt) {
    // 同一语音的 started/finished/stopped/failed 必须按发生顺序到达服务端。
    // 若 started 尚在网络中而 stopped 抢先到达，服务端会忽略 stopped，
    // 随后留下永久的 tts_playing=true，阻塞下一回合播放。
    let lifecycle = Promise.resolve();
    const reportInOrder = (type, error) => {
      lifecycle = lifecycle.then(
        () => reportTtsEvent(type, item, error),
        () => reportTtsEvent(type, item, error),
      );
    };
    return {
      timing: {
        intentId: item.intent_id,
        deliveryReceivedAt,
        screenPublishedAt: window.__voiceLastScreenAt ?? null,
        turnStartedAt: window.__voiceTurnStartedAt ?? null,
        chars: item.voice_text.trim().length,
      },
      speechRate: typeof item.speech_rate === 'number' ? item.speech_rate : 1.0,
      onStarted: () => { ttsStarted(); reportInOrder('tts_started'); },
      onFinished: () => { reportInOrder('tts_finished'); ttsFinished(); },
      onStopped: () => { reportInOrder('tts_stopped'); ttsFinished(); },
      onFailed: error => { reportInOrder('tts_failed', error); ttsFinished(); },
    };
  }
  function playbackEnabled() {
    if (window.phoneEnabled === false) return false;
    if (window.ttsMuted === true) return false;
    const autoSpeak = document.querySelector('#auto-speak');
    return Boolean(autoSpeak?.checked || window.ttsEnabled === true);
  }

  function outcome(code, data) {
    window.dispatchEvent?.(new CustomEvent('voice-delivery-result', {detail: {code}}));
    const conversationId = window.localStorage?.getItem(CONVERSATION_KEY);
    if (conversationId && typeof window.fetch === 'function') {
      const firstItem = Array.isArray(data?.items) ? data.items[0] : null;
      void window.fetch('/voice/runtime/client-result', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          conversation_id: conversationId,
          code,
          authorization: data?.authorization || null,
          reason: data?.reason || null,
          intent_id: firstItem?.intent_id || null,
        }),
      }).catch(() => {});
    }
    return code;
  }

  function validItems(data) {
    if (!Array.isArray(data.items) || data.items.length === 0) return null;
    const items = [];
    const turn = window.conversationTurnStore?.getSnapshot?.();
    for (const item of data.items) {
      if (!item || typeof item.intent_id !== 'string' || !item.intent_id.trim()) return null;
      if (typeof item.kind !== 'string' || !item.kind.trim()) return null;
      if (typeof item.priority !== 'string' || !item.priority.trim()) return null;
      if (typeof item.voice_text !== 'string' || !item.voice_text.trim()) return null;
      if (typeof item.source_block_id !== 'string' || !item.source_block_id.trim()) return null;
      if (turn && !turn.blocks.some(block => block.block_id === item.source_block_id)) return null;
      items.push({...item, voice_text: item.voice_text.trim()});
    }
    return items;
  }

  function consumeVoiceDelivery(data) {
    const deliveryReceivedAt = now();
    if (!data || data.type !== 'voice_delivery') return 'IGNORED_EVENT';
    if (data.authorization === 'CONTENT_ELIGIBLE') return 'CANDIDATE_ONLY';
    if (data.authorization === 'DEFERRED') return 'DEFERRED';
    if (data.authorization === 'DROP') return 'DROPPED';
    if (data.authorization !== 'READY' && data.authorization !== 'PREEMPT') {
      return 'REJECTED_AUTHORIZATION';
    }

    const items = validItems(data);
    if (!items) return outcome('REJECTED_PAYLOAD', data);
    if (!playbackEnabled()) return outcome('PLAYBACK_DISABLED', data);

    if (data.authorization === 'PREEMPT') {
      window.stopSpeech?.();
      if (typeof window.speak === 'function') window.speak(items[0].voice_text, runtimeHooks(items[0], deliveryReceivedAt));
      else if (typeof window.enqueueSpeech === 'function') window.enqueueSpeech(items[0].voice_text, runtimeHooks(items[0], deliveryReceivedAt));
      else return outcome('TTS_UNAVAILABLE');
      for (const item of items.slice(1)) window.enqueueSpeech?.(item.voice_text, runtimeHooks(item, deliveryReceivedAt));
      return outcome('PREEMPTED_AND_PLAYED', data);
    }

    if (typeof window.enqueueSpeech !== 'function') return outcome('TTS_UNAVAILABLE');
    for (const item of items) window.enqueueSpeech(item.voice_text, runtimeHooks(item, deliveryReceivedAt));
    return outcome('PLAYED', data);
  }

  window.consumeVoiceDelivery = consumeVoiceDelivery;
})();
