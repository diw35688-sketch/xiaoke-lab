const assert = require('assert');
global.document = {head: {appendChild() {}}, createElement() { return {textContent: ''}; }};
global.window = {};
require('../../web/frontend/conversation_block_view.js');

const view = window.conversationBlockView;
assert.strictEqual(view({type: 'protocol_card', payload: {title: '缓冲液方案'}}).label, '实验方案');
assert.strictEqual(view({type: 'step_card', payload: {number: 2, title: '调 pH'}}).label, '步骤 2');
assert.strictEqual(view({type: 'safety_alert', payload: {name: '盐酸', critical: true, statements: ['腐蚀性']}}).tone, 'danger');
assert.deepStrictEqual(view({type: 'record_card', payload: {segment_id: 3, transcript: '加入盐酸', entities: {amount: '5mL'}}}).meta, ['amount = 5mL']);
assert.strictEqual(view({type: 'tool_card', payload: {title: '查询', status: 'error'}}).tone, 'danger');
assert.strictEqual(view({type: 'confirmation_card', payload: {text: '是否确认？'}}).label, '待确认');
assert.strictEqual(view({type: 'system_status', payload: {text: '处理中', running: true}}).status, '进行中');
assert.strictEqual(view({type: 'assistant_text', payload: {text: '普通气泡'}}), null);
console.log('conversation_block_view: OK');
