const assert = require('assert');

let options = null;
let starts = 0;
let pauses = 0;
let destroys = 0;
const fakeInstance = {
  start() { starts += 1; },
  pause() { pauses += 1; },
  destroy() { destroys += 1; },
};
const fakeWindow = {
  fetch: async () => ({ok: true, async arrayBuffer() { return new ArrayBuffer(1); }}),
  performance: {now: () => Date.now()},
  ort: {},
  vad: {
    MicVAD: {
      async new(received) {
        options = received;
        return fakeInstance;
      },
    },
  },
};
const fakeDocument = {head: {appendChild() {}}, createElement() { return {}; }};

const {createCallSileroVad} = require('../../web/frontend/call_silero_vad.js');

(async () => {
  const events = [];
  const failures = [];
  let misfires = 0;
  const adapter = await createCallSileroVad({
    onEvent(type, payload) { events.push([type, payload]); },
    onFailure(error) { failures.push(error.message); },
    onMisfire() { misfires += 1; },
  }, {window: fakeWindow, document: fakeDocument});

  assert.strictEqual(options.model, 'v5');
  assert.strictEqual(options.baseAssetPath, '/static/vendor/voice/');
  assert.strictEqual(options.onnxWASMBasePath, '/static/vendor/voice/');
  assert.strictEqual(options.redemptionMs, 1500);
  assert.strictEqual(options.preSpeechPadMs, 450);
  assert.strictEqual(options.minSpeechMs, 1200);

  // 固定噪音概率样例：没有开始事件时，低概率帧不得创建语音段。
  for (const probability of [0.01, 0.08, 0.14, 0.22]) {
    options.onFrameProcessed({isSpeech: probability}, new Float32Array(512));
  }
  assert.deepStrictEqual(events, []);

  // 固定人声概率样例：开始 → 短暂停顿 → 同段继续 → 停顿 → 固化。
  const audio = new Float32Array(16000 * 2);
  options.onSpeechStart();
  options.onFrameProcessed({isSpeech: 0.1}, new Float32Array(512));
  options.onFrameProcessed({isSpeech: 0.7}, new Float32Array(512));
  options.onSpeechEnd(audio);
  assert.deepStrictEqual(events.map(item => item[0]), [
    'speech_started',
    'speech_paused',
    'speech_resumed',
    'speech_paused',
    'segment_finalized',
  ]);
  assert.strictEqual(events[4][1], audio);

  options.onSpeechStart();
  options.onVADMisfire();
  assert.strictEqual(misfires, 1);

  options.onError(new Error('inference failed'));
  options.onError(new Error('duplicate failure'));
  assert.deepStrictEqual(failures, ['inference failed']);

  adapter.start();
  adapter.stop();
  assert.strictEqual(starts, 1);
  assert.strictEqual(pauses, 1);
  assert.strictEqual(destroys, 1);

  console.log('call_silero_vad: OK');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
