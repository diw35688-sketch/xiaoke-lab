const assert = require('assert');

const calls = [];
global.document = {
  querySelector(selector) {
    return selector === '#auto-speak' ? {checked: true} : null;
  },
};
global.CustomEvent = function (type, options) { this.type = type; this.detail = options.detail; };
global.window = {
  ttsEnabled: false,
  dispatchEvent(event) { calls.push(['event', event.detail.code]); },
  stopSpeech() { calls.push(['stop']); },
  speak(text, runtime) { calls.push(['speak', text, runtime]); },
  enqueueSpeech(text, runtime) { calls.push(['enqueue', text, runtime]); },
};

require('../../web/frontend/voice_delivery_client.js');

const item = (id, text) => ({
  intent_id: id,
  kind: 'clarification',
  priority: 'ACTIVE_QUESTION',
  voice_text: text,
  source_block_id: `turn-1:block:${id}`,
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
assert.strictEqual(calls[0][0], 'enqueue');
assert.strictEqual(calls[0][1], '加热多久？');
assert.strictEqual(typeof calls[0][2].onStarted, 'function');
assert.strictEqual(typeof calls[0][2].onFinished, 'function');
assert.strictEqual(typeof calls[0][2].onStopped, 'function');
assert.strictEqual(typeof calls[0][2].onFailed, 'function');
assert.strictEqual(calls[1][0], 'enqueue');
assert.strictEqual(calls[1][1], '请注意安全。');
assert.deepStrictEqual(calls[2], ['event', 'PLAYED']);

calls.length = 0;
assert.strictEqual(window.consumeVoiceDelivery(event('PREEMPT', [
  item('safe-1', '立即停止加热。'),
  item('safe-2', '关闭电源。'),
])), 'PREEMPTED_AND_PLAYED');
assert.strictEqual(calls[0][0], 'stop');
assert.strictEqual(calls[1][0], 'speak');
assert.strictEqual(calls[1][1], '立即停止加热。');
assert.strictEqual(calls[2][0], 'enqueue');
assert.strictEqual(calls[2][1], '关闭电源。');
assert.deepStrictEqual(calls[3], ['event', 'PREEMPTED_AND_PLAYED']);

calls.length = 0;
assert.strictEqual(window.consumeVoiceDelivery(event('READY', [])), 'REJECTED_PAYLOAD');
assert.strictEqual(window.consumeVoiceDelivery(event('READY', [{voice_text: '缺字段'}])), 'REJECTED_PAYLOAD');
assert.strictEqual(window.consumeVoiceDelivery(event('READY', [{
  intent_id: 'missing-source', kind: 'clarification', priority: 'ACTIVE_QUESTION', voice_text: '缺来源'
}])), 'REJECTED_PAYLOAD');
assert.deepStrictEqual(calls, [
  ['event', 'REJECTED_PAYLOAD'],
  ['event', 'REJECTED_PAYLOAD'],
  ['event', 'REJECTED_PAYLOAD'],
]);

calls.length = 0;
window.ttsMuted = true;
assert.strictEqual(window.consumeVoiceDelivery(event('READY')), 'PLAYBACK_DISABLED');
assert.deepStrictEqual(calls, [['event', 'PLAYBACK_DISABLED']]);

console.log('voice_delivery_client: OK');
