// Unified Web Turn transport. Input adapters provide text or WAV; business mode stays orthogonal.
(() => {
  const CONVERSATION_KEY = 'lab-agent-conversation-id';
  const LAB_SESSION_KEY = 'lab-agent-lab-session-id';

  function identity(prefix) {
    if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function localLabSessionId() {
    let value = localStorage.getItem(LAB_SESSION_KEY);
    if (!value) {
      value = identity('lab');
      localStorage.setItem(LAB_SESSION_KEY, value);
    }
    return value;
  }

  const initialLabSessionId = localStorage.getItem(LAB_SESSION_KEY);
  const labSessionReady = fetch('/record/history').then(response => {
    if (!response.ok) throw new Error('无法读取当前实验会话');
    return response.json();
  }).then(data => {
    // Unified Turn sessions are browser-owned after the first migration load.
    // Do not overwrite a newer locally persisted session with the legacy
    // /record/history global session when the page is refreshed.
    if (!initialLabSessionId && data.session_id) {
      localStorage.setItem(LAB_SESSION_KEY, data.session_id);
    }
    return localLabSessionId();
  }).catch(() => localLabSessionId());

  function beginNextLabSession(completedEvent) {
    const previous = localLabSessionId();
    const next = identity('lab');
    localStorage.setItem(LAB_SESSION_KEY, next);
    window.dispatchEvent(new CustomEvent('turn-experiment-session-ended', {
      detail: {
        previous_lab_session_id: previous,
        next_lab_session_id: next,
        request_id: completedEvent?.turn?.request_id || null,
        turn_id: completedEvent?.turn?.turn_id || null,
      },
    }));
  }

  async function metadata(snapshot, ids) {
    const experiment = snapshot.interaction_mode === 'experiment';
    return {
      conversation_id: localStorage.getItem(CONVERSATION_KEY) || null,
      request_id: ids.request_id,
      turn_id: ids.turn_id,
      lab_session_id: experiment ? (await labSessionReady, localLabSessionId()) : null,
      interaction_mode: snapshot.interaction_mode,
      experiment_context: snapshot.experiment_context,
      mode_version: snapshot.mode_version,
    };
  }

  async function consume(response, onEvent) {
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.detail || `Turn 请求失败（${response.status}）`);
    }
    if (!response.body) throw new Error('浏览器不支持 SSE 响应流');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const browserTiming = {request_started: performance.now()};
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value || new Uint8Array(), {stream: !chunk.done});
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const line = raw.split('\n').find(item => item.startsWith('data: '));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === 'turn_accepted' && event.conversation_id) {
          localStorage.setItem(CONVERSATION_KEY, event.conversation_id);
          browserTiming.accepted = performance.now();
        } else if (event.type === 'turn_result') {
          browserTiming.screen_published = performance.now();
          if (event.business?.session_ended === true && !event.replayed) {
            beginNextLabSession(event);
          }
        } else if (event.type === 'voice_delivery') {
          browserTiming.voice_delivery_received = performance.now();
        }
        await onEvent?.(event, browserTiming);
      }
      if (chunk.done) break;
    }
    console.info('[turn-timing]', browserTiming);
  }

  async function submitText(text, options) {
    const ids = {
      request_id: options.requestId || identity('web'),
      turn_id: options.turnId || identity('turn'),
    };
    const body = {...await metadata(options.modeSnapshot, ids), text};
    const response = await fetch('/turn/text', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body), signal: options.signal,
    });
    return consume(response, options.onEvent);
  }

  async function submitAudio(blob, options) {
    const ids = {
      request_id: options.requestId || identity('web-audio'),
      turn_id: options.turnId || identity('turn-audio'),
    };
    const info = {
      ...await metadata(options.modeSnapshot, ids),
      input_source: options.inputSource,
    };
    const form = new FormData();
    form.append('audio', blob, options.filename || 'segment.wav');
    form.append('metadata', JSON.stringify(info));
    const response = await fetch('/turn/audio', {
      method: 'POST', body: form, signal: options.signal,
    });
    return consume(response, options.onEvent);
  }

  window.turnClient = {submitText, submitAudio, identity, labSessionId: localLabSessionId};
})();
