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
    await window.publishProtocolContextBlocks?.(turnId);
    return {request_id: identity, turn_id: turnId};
  };

  window.publishProtocolContextBlocks = async turnId => {
    if (!store || !turnId) return;
    const path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session/steps')
      : '/protocols/session/steps';
    const response = await fetch(path);
    if (!response.ok) return;
    const data = await response.json();
    if (data.mode !== 'protocol') {
      store.upsertBlock({block_id: `${turnId}:protocol`, type: 'protocol_card', payload: {
        title: '自由实验记录', summary: '当前没有方案约束，仍会保留必要的语义追问。', status: 'free',
      }});
      return;
    }
    store.upsertBlock({block_id: `${turnId}:protocol`, type: 'protocol_card', payload: {
      title: data.protocol.title, summary: `共 ${data.protocol.total_steps} 步`, status: 'protocol',
    }});
    const step = data.step;
    store.upsertBlock({block_id: `${turnId}:step:${step.number}`, type: 'step_card', payload: {
      number: step.number, title: step.title, instruction: step.instruction,
      lines: (step.substeps || []).map(item => item.text),
      meta: [`方案已知 ${Object.keys(step.protocol_values || {}).length} 项`, `现场必测 ${(step.must_record || []).length} 项`],
    }});
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
