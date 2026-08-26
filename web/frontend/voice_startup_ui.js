// 页面启动欢迎与语音栈可见进度。播放仍只接受后端 voice_delivery 授权。
(() => {
  const store = window.conversationTurnStore;
  if (!store) return;

  const identity = `startup-${Date.now()}`;
  const turnId = `turn-${identity}`;
  const blockId = `${turnId}:voice-startup`;
  const states = {
    tts_warmup: '云端语音：准备中',
    silero_assets: '人声检测资源：准备中',
    microphone: '麦克风与人声检测：等待授权',
    asr_warmup: '语音识别模型：准备中',
  };

  function modeName(snapshot) {
    if (snapshot.interaction_mode === 'chat') return 'chat';
    return snapshot.experiment_context === 'protocol' ? 'protocol' : 'free';
  }
  function line(component, state, detail) {
    const labels = {
      tts_warmup: '云端语音', silero_assets: '人声检测资源',
      microphone: '麦克风与人声检测', asr_warmup: '语音识别模型',
    };
    if (!labels[component]) return null;
    const suffix = state === 'ready' ? '已就绪' : state === 'error' ? `未就绪${detail ? `（${detail}）` : ''}` : '准备中';
    return `${labels[component]}：${suffix}`;
  }
  function payload() {
    const values = Object.values(states);
    const finished = values.filter(value => value.includes('已就绪')).length;
    const failed = values.some(value => value.includes('未就绪'));
    return {
      kind: 'voice_startup', title: '语音功能启动',
      text: finished === values.length ? '全部准备完成，可以开始连续通话。' : `正在准备语音功能（${finished}/4）`,
      lines: values, running: finished !== values.length && !failed,
      status: failed ? '部分功能异常' : (finished === values.length ? '已就绪' : ''), error: failed,
    };
  }
  function publish() {
    const current = store.getSnapshot();
    if (current?.turn_id === turnId) {
      store.upsertBlock({block_id: blockId, type: 'system_status', payload: payload()});
      return;
    }
    const row = document.querySelector(`[data-block-id="${blockId}"]`);
    const view = window.conversationBlockView?.({type: 'system_status', payload: payload()});
    if (row && view) {
      row.className = `message block-card tone-${view.tone}`;
      row.querySelector('.status').textContent = view.status;
      row.querySelector('.chat-block-lines').textContent = view.lines.join('\n');
    }
  }

  const mode = window.interactionModeState.current();
  const localNow = new Date();
  const existingConversation = localStorage.getItem('lab-agent-conversation-id');
  store.beginTurn({
    conversation_id: existingConversation || `startup-pending-${Date.now()}`,
    request_id: identity, turn_id: turnId, ...mode, input_source: 'text', blocks: [],
  });
  publish();

  window.addEventListener('lab:voice-startup-progress', event => {
    const detail = event.detail || {};
    const next = line(detail.component, detail.state, detail.detail);
    if (next) { states[detail.component] = next; publish(); }
  });

  fetch('/voice/runtime/startup', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      conversation_id: existingConversation || null,
      source_block_id: blockId,
      local_hour: localNow.getHours(),
      local_minute: localNow.getMinutes(),
      mode: modeName(mode),
    }),
  }).then(response => {
    if (!response.ok) throw new Error('启动欢迎语授权失败');
    return response.json();
  }).then(data => {
    localStorage.setItem('lab-agent-conversation-id', data.conversation_id);
    const current = store.getSnapshot();
    if (current?.turn_id === turnId && current.conversation_id !== data.conversation_id) {
      store.clear();
      store.beginTurn({
        conversation_id: data.conversation_id, request_id: identity, turn_id: turnId,
        ...mode, input_source: 'text',
        blocks: [{block_id: blockId, type: 'system_status', payload: payload()}],
      });
    }
    // 启动欢迎是用户明确要求的一次性播报；临时勾选只覆盖这次正式授权，
    // 随即恢复，不改变后续回答是否自动朗读的个人设置。
    const autoSpeak = document.querySelector('#auto-speak');
    const wasChecked = Boolean(autoSpeak?.checked);
    if (autoSpeak) autoSpeak.checked = true;
    (data.voice_delivery_events || []).forEach(event => window.consumeVoiceDelivery?.(event));
    if (autoSpeak) autoSpeak.checked = wasChecked;
  }).catch(error => {
    console.warn('[voice-startup] 欢迎语未播放：', error);
  });
})();
