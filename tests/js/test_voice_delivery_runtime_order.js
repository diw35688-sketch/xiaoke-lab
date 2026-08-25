const assert = require('assert');

const requests = [];
let releaseStarted;
global.document = {
  querySelector(selector) {
    return selector === '#auto-speak' ? {checked: true} : null;
  },
};
global.CustomEvent = function (type, options) { this.type = type; this.detail = options.detail; };
global.fetch = (_url, options) => {
  const body = JSON.parse(options.body);
  requests.push(body.type);
  if (body.type === 'tts_started') {
    return new Promise(resolve => { releaseStarted = () => resolve({
      ok: true,
      json: () => Promise.resolve({voice_delivery_events: []}),
    }); });
  }
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({voice_delivery_events: []}),
  });
};
let hooks;
global.window = {
  ttsEnabled: true,
  localStorage: {getItem() { return 'conversation-order'; }},
  conversationTurnStore: {getSnapshot() { return null; }},
  dispatchEvent() {},
  enqueueSpeech(_text, runtime) { hooks = runtime; },
};

require('../../web/frontend/voice_delivery_client.js');

(async () => {
  window.consumeVoiceDelivery({
    type: 'voice_delivery',
    authorization: 'READY',
    items: [{
      intent_id: 'intent-order',
      kind: 'assistant_reply',
      priority: 'REVIEW',
      voice_text: '测试事件顺序。',
      source_block_id: 'turn-order:spoken',
    }],
  });

  hooks.onStarted();
  hooks.onStopped();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepStrictEqual(requests, ['tts_started']);

  releaseStarted();
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.deepStrictEqual(requests, ['tts_started', 'tts_stopped']);
  console.log('voice delivery runtime event order test passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
