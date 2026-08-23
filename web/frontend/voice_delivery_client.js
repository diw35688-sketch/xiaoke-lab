// Frontend boundary for backend-owned voice playback authorization.
// CONTENT_ELIGIBLE is only a content candidate; only READY/PREEMPT may reach TTS.
(() => {
  function playbackEnabled() {
    if (window.ttsMuted === true) return false;
    const autoSpeak = document.querySelector('#auto-speak');
    return Boolean(autoSpeak?.checked || window.ttsEnabled === true);
  }

  function validItems(data) {
    if (!Array.isArray(data.items) || data.items.length === 0) return null;
    const items = [];
    for (const item of data.items) {
      if (!item || typeof item.intent_id !== 'string' || !item.intent_id.trim()) return null;
      if (typeof item.kind !== 'string' || !item.kind.trim()) return null;
      if (typeof item.priority !== 'string' || !item.priority.trim()) return null;
      if (typeof item.voice_text !== 'string' || !item.voice_text.trim()) return null;
      items.push({...item, voice_text: item.voice_text.trim()});
    }
    return items;
  }

  function consumeVoiceDelivery(data) {
    if (!data || data.type !== 'voice_delivery') return 'IGNORED_EVENT';
    if (data.authorization === 'CONTENT_ELIGIBLE') return 'CANDIDATE_ONLY';
    if (data.authorization === 'DEFERRED') return 'DEFERRED';
    if (data.authorization === 'DROP') return 'DROPPED';
    if (data.authorization !== 'READY' && data.authorization !== 'PREEMPT') {
      return 'REJECTED_AUTHORIZATION';
    }

    const items = validItems(data);
    if (!items) return 'REJECTED_PAYLOAD';
    if (!playbackEnabled()) return 'PLAYBACK_DISABLED';

    if (data.authorization === 'PREEMPT') {
      window.stopSpeech?.();
      if (typeof window.speak === 'function') window.speak(items[0].voice_text);
      else if (typeof window.enqueueSpeech === 'function') window.enqueueSpeech(items[0].voice_text);
      else return 'TTS_UNAVAILABLE';
      for (const item of items.slice(1)) window.enqueueSpeech?.(item.voice_text);
      return 'PREEMPTED_AND_PLAYED';
    }

    if (typeof window.enqueueSpeech !== 'function') return 'TTS_UNAVAILABLE';
    for (const item of items) window.enqueueSpeech(item.voice_text);
    return 'PLAYED';
  }

  window.consumeVoiceDelivery = consumeVoiceDelivery;
})();
