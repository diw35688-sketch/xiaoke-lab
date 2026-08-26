// 单聊天时间线的唯一前端事实源。
// 本模块只保存当前 Turn/Block；不渲染 DOM、不保存实验、不执行 Tool、不播放 TTS。
(() => {
  const VISIBLE_TYPES = new Set([
    'user_text', 'assistant_text', 'protocol_card', 'step_card',
    'safety_alert', 'record_card', 'tool_card', 'confirmation_card',
    'system_status',
  ]);

  const clone = value => JSON.parse(JSON.stringify(value));
  const required = (value, name) => {
    if (typeof value !== 'string' || !value.trim()) throw new Error(`${name} 不能为空`);
  };

  function createConversationTurnStore() {
    let turn = null;
    let requestFingerprint = null;
    const listeners = new Set();

    function snapshot() {
      return turn ? clone(turn) : null;
    }
    function publish() {
      const value = snapshot();
      listeners.forEach(listener => listener(value));
    }
    function beginTurn(input) {
      const next = clone(input || {});
      required(next.conversation_id, 'conversation_id');
      required(next.request_id, 'request_id');
      required(next.turn_id, 'turn_id');
      if (!['chat', 'experiment'].includes(next.interaction_mode)) throw new Error('interaction_mode 非法');
      if (!['none', 'free', 'protocol'].includes(next.experiment_context)) throw new Error('experiment_context 非法');
      if (next.interaction_mode === 'chat' && next.experiment_context !== 'none') throw new Error('chat 模式上下文冲突');
      if (next.interaction_mode === 'experiment' && next.experiment_context === 'none') throw new Error('experiment 模式上下文冲突');
      if (!Number.isInteger(next.mode_version) || next.mode_version <= 0) throw new Error('mode_version 必须是正整数');
      if (!['text', 'single_recording', 'continuous_call'].includes(next.input_source)) throw new Error('input_source 非法');
      if (!Array.isArray(next.blocks)) next.blocks = [];
      const key = `${next.conversation_id}:${next.request_id}`;
      const fingerprint = JSON.stringify(next);
      if (turn && `${turn.conversation_id}:${turn.request_id}` === key) {
        if (requestFingerprint === fingerprint) return snapshot();
        throw new Error('同一 request_id 的 Turn 内容发生冲突');
      }
      turn = next;
      requestFingerprint = fingerprint;
      publish();
      return snapshot();
    }
    function upsertBlock(block) {
      if (!turn) throw new Error('必须先 beginTurn');
      const next = clone(block || {});
      required(next.block_id, 'block_id');
      if (!VISIBLE_TYPES.has(next.type)) throw new Error('未知 block type');
      const index = turn.blocks.findIndex(item => item.block_id === next.block_id);
      if (index >= 0) turn.blocks[index] = next;
      else turn.blocks.push(next);
      publish();
      return clone(next);
    }
    function pushThink(text, running) {
      return upsertBlock({
        block_id: `${turn.turn_id}:think`,
        type: 'system_status',
        payload: { kind: 'think', text: String(text || ''), running: Boolean(running) },
      });
    }
    function pushTool(view) {
      const safe = clone(view || {});
      const identity = safe.intent_id || safe.tool_call_id || safe.title;
      required(identity, 'tool identity');
      return upsertBlock({
        block_id: `${turn.turn_id}:tool:${identity}`,
        type: 'tool_card',
        payload: safe,
      });
    }
    function clear() {
      turn = null;
      requestFingerprint = null;
      publish();
    }
    function subscribe(listener) {
      if (typeof listener !== 'function') throw new TypeError('listener 必须是函数');
      listeners.add(listener);
      listener(snapshot());
      return () => listeners.delete(listener);
    }

    return { beginTurn, upsertBlock, pushThink, pushTool, clear, subscribe, getSnapshot: snapshot };
  }

  window.createConversationTurnStore = createConversationTurnStore;
  window.conversationTurnStore = createConversationTurnStore();
})();
