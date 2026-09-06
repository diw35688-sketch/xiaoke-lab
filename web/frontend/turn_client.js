// Unified Web Turn transport. Input adapters provide text or WAV; business mode stays orthogonal.
(() => {
  const CONVERSATION_KEY = 'lab-agent-conversation-id';
  const LAB_SESSIONS_KEY = 'lab-agent-lab-sessions';
  const FRESH_CHAT_KEY = 'lab-agent-fresh-chat';

  function identity(prefix) {
    if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
    return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function readSessions() {
    try {
      const raw = localStorage.getItem(LAB_SESSIONS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function writeSessions(map) {
    localStorage.setItem(LAB_SESSIONS_KEY, JSON.stringify(map));
  }

  function labSessionKey(snapshot) {
    return snapshot.experiment_context === 'protocol'
      ? `protocol:${snapshot.protocol_id || ''}`
      : snapshot.experiment_context;
  }

  function localLabSessionId(modeKey) {
    const sessions = readSessions();
    if (!sessions[modeKey]) {
      sessions[modeKey] = identity('lab');
      writeSessions(sessions);
    }
    return sessions[modeKey];
  }

  function protocolSessionIdentity() {
    const snapshot = window.interactionModeState.current();
    let conversationId = localStorage.getItem(CONVERSATION_KEY);
    if (!conversationId) {
      conversationId = identity('conversation');
      localStorage.setItem(CONVERSATION_KEY, conversationId);
    }
    return {
      conversation_id: conversationId,
      lab_session_id: localLabSessionId(labSessionKey(snapshot)),
    };
  }

  function protocolSessionUrl(path) {
    const ids = protocolSessionIdentity();
    return path + '?conversation_id=' + encodeURIComponent(ids.conversation_id)
      + '&lab_session_id=' + encodeURIComponent(ids.lab_session_id);
  }

  async function moveProtocolStep(action, stepNumber) {
    const ids = protocolSessionIdentity();
    const response = await fetch('/protocols/session/move', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        ...ids,
        action,
        step_number: stepNumber == null ? null : stepNumber,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = result.detail || {};
      throw new Error(
        typeof detail === 'string'
          ? detail
          : (detail.reason || '方案步骤切换失败')
      );
    }
    return result;
  }

  function clearSession() {
    localStorage.removeItem(CONVERSATION_KEY);
    localStorage.removeItem(LAB_SESSIONS_KEY);
    localStorage.setItem(FRESH_CHAT_KEY, '1');
  }

  function beginNextLabSession(completedEvent, modeSnapshot) {
    const modeKey = labSessionKey(modeSnapshot);
    const previous = localLabSessionId(modeKey);
    const next = identity('lab');
    const sessions = readSessions();
    sessions[modeKey] = next;
    writeSessions(sessions);
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
      lab_session_id: experiment ? localLabSessionId(labSessionKey(snapshot)) : null,
      interaction_mode: snapshot.interaction_mode,
      experiment_context: snapshot.experiment_context,
      mode_version: snapshot.mode_version,
    };
  }

  window.protocolSessionIdentity = protocolSessionIdentity;
  window.protocolSessionUrl = protocolSessionUrl;
  window.moveProtocolStep = moveProtocolStep;

  // 切换实验轨道：把指定 lab_session_id 写入 localStorage，再切换交互模式
  async function switchTrack(protocolId, labSessionId, protocolTitle) {
    if (!protocolId || !labSessionId) return;
    // 写入 localStorage，让 protocolSessionIdentity() 返回正确的 lab_session_id
    var modeKey = 'protocol:' + protocolId;
    var sessions = readSessions();
    sessions[modeKey] = labSessionId;
    writeSessions(sessions);
    // 切换交互模式
    window.interactionModeState.select('protocol', protocolId);
    // 通知后端切换会话
    var ids = protocolSessionIdentity();
    try {
      await fetch('/protocols/session', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          protocol_id: protocolId,
          conversation_id: ids.conversation_id,
          lab_session_id: ids.lab_session_id,
        }),
      });
    } catch (_) {}
    // 触发画布刷新
    window.dispatchEvent(new CustomEvent('lab:track-switched', {
      detail: { protocol_id: protocolId, lab_session_id: labSessionId, title: protocolTitle }
    }));
  }
  window.switchTrack = switchTrack;

  // 把服务端 TurnTimingRecorder 快照换算成关键阶段耗时（毫秒）。
  // 服务端只记每个 mark 的 elapsed_ms，差值才是"某一段花了多久"。
  function summarizeServerTiming(timing) {
    if (!timing || typeof timing !== 'object') return null;
    const elapsed = (name) =>
      (timing[name] && typeof timing[name].elapsed_ms === 'number')
        ? timing[name].elapsed_ms : null;
    const span = (from, to) => {
      const a = elapsed(from); const b = elapsed(to);
      return (a == null || b == null) ? null : Math.round(b - a);
    };
    const total = elapsed('persistence_committed')
      ?? elapsed('result_built')
      ?? elapsed('understanding_completed');
    return {
      understanding_llm_ms: span('llm_started', 'llm_completed'),
      understanding_total_ms: span('understanding_started', 'understanding_completed'),
      persistence_ms: span('persistence_started', 'persistence_committed'),
      dispatch_to_result_ms: span('dispatch_started', 'result_built'),
      total_ms: total,
    };
  }

  async function consume(response, onEvent, modeSnapshot) {
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.detail || `Turn 请求失败（${response.status}）`);
    }
    if (!response.body) throw new Error('浏览器不支持 SSE 响应流');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const browserTiming = {request_started: performance.now()};
    let serverTiming = null;
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
          localStorage.removeItem(FRESH_CHAT_KEY);
          browserTiming.accepted = performance.now();
        } else if (event.type === 'turn_result') {
          browserTiming.screen_published = performance.now();
          serverTiming = event.timing || null;
          if (event.business?.session_ended === true && !event.replayed) {
            beginNextLabSession(event, modeSnapshot);
          }
        } else if (event.type === 'voice_delivery') {
          browserTiming.voice_delivery_received = performance.now();
        }
        await onEvent?.(event, browserTiming);
      }
      if (chunk.done) break;
    }
    console.info('[turn-timing]', browserTiming, summarizeServerTiming(serverTiming));
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
    return consume(response, options.onEvent, options.modeSnapshot);
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
    return consume(response, options.onEvent, options.modeSnapshot);
  }

  window.turnClient = {submitText, submitAudio, identity, clearSession};
})();
