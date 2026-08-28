const assert = require('assert');

global.window = {};
require('../../web/frontend/conversation_turn_store.js');

const store = window.createConversationTurnStore();
const snapshots = [];
store.subscribe(value => snapshots.push(value));

const base = {
  conversation_id: 'conversation-1',
  request_id: 'request-1',
  turn_id: 'turn-1',
  interaction_mode: 'chat',
  experiment_context: 'none',
  mode_version: 3,
  input_source: 'text',
  blocks: [{block_id: 'user-1', type: 'user_text', payload: {text: '你好'}}],
};

store.beginTurn(base);
store.pushThink('正在判断', true);
store.pushThink('判断完成', false);
assert.strictEqual(store.getSnapshot().blocks.filter(block => block.type === 'system_status').length, 1);
assert.deepStrictEqual(store.getSnapshot().blocks[1].payload, {
  kind: 'think', text: '判断完成', running: false,
});

store.pushTool({tool_call_id: 'call-7', title: '查询时间', status: 'pending', lines: []});
store.pushTool({tool_call_id: 'call-7', title: '查询时间', status: 'done', lines: ['12:30']});
const tools = store.getSnapshot().blocks.filter(block => block.type === 'tool_card');
assert.strictEqual(tools.length, 1);
assert.strictEqual(tools[0].payload.status, 'done');

// Store 已加入运行结果后，原始请求的完全相同重放仍然幂等，不清空已有 Blocks。
assert.strictEqual(store.beginTurn(base).blocks.length, 3);
assert.throws(() => store.beginTurn({...base, mode_version: 4}), /冲突/);

// The committed result may add output Blocks without changing the immutable
// request. It replaces the optimistic runtime view instead of looking like a
// request_id collision.
const committed = {
  ...base,
  blocks: [
    ...base.blocks,
    {block_id: 'assistant-1', type: 'assistant_text', payload: {text: '你好！'}},
  ],
};
assert.strictEqual(store.acceptCommittedTurn(committed).blocks.length, 2);
assert.strictEqual(store.getSnapshot().blocks[1].payload.text, '你好！');
assert.throws(() => store.acceptCommittedTurn({
  ...committed,
  blocks: [
    {block_id: 'user-1', type: 'user_text', payload: {text: '篡改输入'}},
    committed.blocks[1],
  ],
}), /冲突/);

const leaked = store.getSnapshot();
leaked.blocks[0].payload.text = '篡改';
assert.strictEqual(store.getSnapshot().blocks[0].payload.text, '你好');
assert.ok(snapshots.length >= 5);

store.clear();
assert.strictEqual(store.getSnapshot(), null);
console.log('conversation_turn_store: OK');
