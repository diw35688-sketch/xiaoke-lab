// 把现有方案/步骤/安全/记录事实翻译成聊天 Block；不执行其业务动作。
(() => {
  const store = window.conversationTurnStore;

  window.beginRecordSurface = async (transcript, modeSnapshot) => {
    if (!store) return;
    modeSnapshot = modeSnapshot || window.interactionModeState.capture('single_recording');
    const identity = `record-${Date.now()}`;
    const turnId = `turn-${identity}`;
    window.addChatMessage?.(transcript, 'user');
    store.beginTurn({
      conversation_id: localStorage.getItem('lab-agent-conversation-id') || 'record-conversation',
      request_id: identity, turn_id: turnId, ...modeSnapshot,
      blocks: [{block_id: `${turnId}:user`, type: 'user_text', payload: {text: transcript}}],
    });
    // 方案卡片由服务端在明确进入/切换方案时返回；普通口述和聊天不再自动插入方案上下文。
    return {request_id: identity, turn_id: turnId};
  };

  // 方案上下文只在用户明确进入方案/开始实验时展示一次；普通聊天不重复插入整套方案卡片。
  let protocolContextPublished = false;
  window.resetProtocolContextSurface = () => { protocolContextPublished = false; };

  window.publishProtocolContextBlocks = async turnId => {
    if (!store || !turnId || protocolContextPublished) return;
    const path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session/steps')
      : '/protocols/session/steps';
    const response = await fetch(path);
    if (!response.ok) return;
    const data = await response.json();
    if (data.mode !== 'protocol') {
      protocolContextPublished = true;
      store.upsertBlock({block_id: `${turnId}:protocol`, type: 'protocol_card', payload: {
        title: '请先选择实验方案', summary: '当前没有激活方案，请进入方案实验并选择方案。', status: 'protocol',
      }});
      return;
    }
    store.upsertBlock({block_id: `${turnId}:protocol`, type: 'protocol_card', payload: {
      title: data.protocol.title, summary: `共 ${data.protocol.total_steps} 步`, status: 'protocol',
    }});
    const step = data.step;
    if (!step) return;
    protocolContextPublished = true;
    store.upsertBlock({block_id: `${turnId}:step:${step.number}`, type: 'step_card', payload: {
      number: step.number, title: step.title, instruction: step.instruction,
      lines: (step.substeps || []).map(item => item.text),
      meta: [`方案已知 ${Object.keys(step.protocol_values || {}).length} 项`, `现场必测 ${(step.must_record || []).length} 项`],
    }});
    // 步骤卡片更新时，通知实验画布刷新并自动跳转到"实验进行中"视图
    try { window.dispatchEvent(new CustomEvent('lab:experiment-changed')); } catch (_) {}
    try {
      if (window.shellShow) window.shellShow('run');
    } catch (_) {}
    (data.safety || []).forEach((item, index) => store.upsertBlock({
      block_id: `${turnId}:safety:${item.cas || item.name || index}`,
      type: 'safety_alert', payload: {...item, note: data.safety_note},
    }));
  };

  window.publishRecordSurface = data => {
    if (!store || !data) return;
    const snapshot = store.getSnapshot();
    if (!snapshot) return;
    store.upsertBlock({block_id: `${snapshot.turn_id}:record:${data.segment_id}`, type: 'record_card', payload: {
      segment_id: data.segment_id, transcript: data.transcript, entities: data.entities || {}, status: '已保存',
    }});
    (data.messages || []).forEach((message, index) => {
      if (message.kind === 'confirmation_ack' || message.kind === 'clarification') {
        store.upsertBlock({block_id: `${snapshot.turn_id}:confirmation:${message.intent_id || index}`,
          type: 'confirmation_card', payload: {title: message.kind === 'clarification' ? '需要补充' : '确认结果', text: message.text, status: message.kind}});
      }
    });
  };
})();
