const assert = require('assert');

const played = [];
global.document = {querySelector: () => ({checked: true})};
global.window = {
  ttsEnabled: true,
  enqueueSpeech(text) { played.push(text); },
};
require('../../web/frontend/conversation_turn_store.js');
require('../../web/frontend/voice_delivery_client.js');

function base(producer, mode, context, version) {
  return {
    conversation_id: `conversation-${producer}`,
    request_id: `request-${producer}`,
    turn_id: `turn-${producer}`,
    interaction_mode: mode,
    experiment_context: context,
    mode_version: version,
    input_source: producer === 'record' ? 'single_recording' : 'text',
    blocks: [{
      block_id: `turn-${producer}:user`, type: 'user_text', payload: {text: producer},
    }],
  };
}

const cases = [
  ['chat', 'chat', 'none', 'assistant_text', 'assistant'],
  ['record', 'experiment', 'free', 'confirmation_card', 'confirmation:ask-record'],
  ['tool', 'chat', 'none', 'tool_card', 'tool:call-1'],
];

for (const [producer, mode, context, blockType, suffix] of cases) {
  const request = base(producer, mode, context, 2);
  window.conversationTurnStore.beginTurn(request);
  const source = `turn-${producer}:${suffix}`;
  window.conversationTurnStore.upsertBlock({
    block_id: source, type: blockType, payload: {text: `${producer} visible`},
  });
  const result = window.consumeVoiceDelivery({
    type: 'voice_delivery', authorization: 'READY', items: [{
      intent_id: `intent-${producer}`, kind: 'clarification',
      priority: 'ACTIVE_QUESTION', voice_text: `${producer} voice`,
      source_block_id: source,
    }],
  });
  assert.strictEqual(result, 'PLAYED');
  // 完全相同请求重放保持运行中新增的 Block。
  assert.strictEqual(window.conversationTurnStore.beginTurn(request).blocks.length, 2);
  assert.throws(
    () => window.conversationTurnStore.beginTurn({...request, mode_version: 3}),
    /冲突/,
  );
  window.conversationTurnStore.clear();
}

window.conversationTurnStore.beginTurn(base('bad', 'chat', 'none', 1));
assert.strictEqual(window.consumeVoiceDelivery({
  type: 'voice_delivery', authorization: 'READY', items: [{
    intent_id: 'orphan', kind: 'clarification', priority: 'ACTIVE_QUESTION',
    voice_text: 'orphan voice', source_block_id: 'turn-bad:missing',
  }],
}), 'REJECTED_PAYLOAD');

assert.deepStrictEqual(played, ['chat voice', 'record voice', 'tool voice']);
console.log('three_producer_matrix: OK');
