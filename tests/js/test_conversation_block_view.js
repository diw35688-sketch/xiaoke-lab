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
// 2026-08-29 修正：1889cd0 起 label 为「待确认问题」，测试此前未跟上（Node 测试不在 unittest 发现范围，曾静默漂移）
assert.strictEqual(view({type: 'confirmation_card', payload: {text: '是否确认？'}}).label, '待确认问题');
assert.strictEqual(view({type: 'system_status', payload: {text: '处理中', running: true}}).status, '进行中');
assert.strictEqual(view({type: 'assistant_text', payload: {text: '普通气泡'}}), null);
// 语音启动自检：正常/进行中不刷聊天流（进度归小科状态条），失败才落警示卡片。
assert.strictEqual(view({type: 'system_status', payload: {kind: 'voice_startup', text: '正在准备语音功能（2/4）', running: true}}), null);
assert.strictEqual(view({type: 'system_status', payload: {kind: 'voice_startup', text: '全部准备完成', running: false}}), null);
assert.strictEqual(view({type: 'system_status', payload: {kind: 'voice_startup', error: true, status: '部分功能异常', text: '语音未就绪'}}).tone, 'danger');
console.log('conversation_block_view: OK');
