const assert = require('assert');

const calls = [];
global.document = {
  querySelector(selector) {
    return selector === '#auto-speak' ? {checked: true} : null;
  },
};
global.window = {
  ttsEnabled: false,
  stopSpeech() { calls.push(['stop']); },
  speak(text) { calls.push(['speak', text]); },
  enqueueSpeech(text) { calls.push(['enqueue', text]); },
};

require('../../web/frontend/voice_delivery_client.js');

const item = (id, text) => ({
  intent_id: id,
  kind: 'clarification',
  priority: 'ACTIVE_QUESTION',
  voice_text: text,
});

function event(authorization, items = [item('ask-1', '加热多久？')]) {
  return {type: 'voice_delivery', authorization, items};
}

assert.strictEqual(window.consumeVoiceDelivery(event('CONTENT_ELIGIBLE')), 'CANDIDATE_ONLY');
assert.strictEqual(window.consumeVoiceDelivery(event('DEFERRED')), 'DEFERRED');
assert.strictEqual(window.consumeVoiceDelivery(event('DROP')), 'DROPPED');
assert.strictEqual(window.consumeVoiceDelivery(event('UNKNOWN')), 'REJECTED_AUTHORIZATION');
assert.deepStrictEqual(calls, []);

assert.strictEqual(window.consumeVoiceDelivery(event('READY', [
  item('ask-1', ' 加热多久？ '),
  item('ack-1', '请注意安全。'),
])), 'PLAYED');
assert.deepStrictEqual(calls, [
  ['enqueue', '加热多久？'],
  ['enqueue', '请注意安全。'],
]);

calls.length = 0;
assert.strictEqual(window.consumeVoiceDelivery(event('PREEMPT', [
  item('safe-1', '立即停止加热。'),
  item('safe-2', '关闭电源。'),
])), 'PREEMPTED_AND_PLAYED');
assert.deepStrictEqual(calls, [
  ['stop'],
  ['speak', '立即停止加热。'],
  ['enqueue', '关闭电源。'],
]);

calls.length = 0;
assert.strictEqual(window.consumeVoiceDelivery(event('READY', [])), 'REJECTED_PAYLOAD');
assert.strictEqual(window.consumeVoiceDelivery(event('READY', [{voice_text: '缺字段'}])), 'REJECTED_PAYLOAD');
assert.deepStrictEqual(calls, []);

console.log('voice_delivery_client: OK');
