const assert = require('assert');

const fetched = [];
const started = [];
global.document = {
  querySelector() { return null; },
  getElementById() { return {classList: {contains() { return true; }}}; },
};

class FakeSource {
  constructor(context) { this.context = context; this.onended = null; }
  connect() {}
  disconnect() {}
  start(at) {
    started.push(at);
    queueMicrotask(() => this.onended?.());
  }
  stop() { queueMicrotask(() => this.onended?.()); }
}
class FakeAudioContext {
  constructor() { this.currentTime = 0; this.state = 'running'; this.destination = {}; }
  createBuffer(_channels, length, sampleRate) {
    return {duration: length / sampleRate, copyToChannel() {}};
  }
  createBufferSource() { return new FakeSource(this); }
  resume() { return Promise.resolve(); }
}

global.window = {
  ttsMuted: false,
  AudioContext: FakeAudioContext,
  dispatchAvatarState() {},
  setTimeout(callback) { queueMicrotask(callback); },
  performance: {now: () => Date.now()},
};

function pcmResponse() {
  let sent = false;
  return {
    ok: true,
    headers: {get(name) {
      if (name === 'X-Audio-Format') return 'pcm_s16le';
      if (name === 'X-Audio-Sample-Rate') return '24000';
      return null;
    }},
    body: {getReader() { return {
      read() {
        if (sent) return Promise.resolve({done: true});
        sent = true;
        return Promise.resolve({done: false, value: new Uint8Array([0, 0, 1, 0])});
      },
      releaseLock() {},
    }; }},
  };
}

global.fetch = (url, options) => {
  if (url === '/tts/warmup') return Promise.resolve({ok: true});
  const text = JSON.parse(options.body).text;
  fetched.push([url, text]);
  if (text === '旧回复。') {
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => {
        const error = new Error('aborted'); error.name = 'AbortError'; reject(error);
      });
    });
  }
  return Promise.resolve(pcmResponse());
};

require('../../web/frontend/local_tts.js');

(async () => {
  window.enqueueSpeech('旧回复。');
  await new Promise(resolve => setImmediate(resolve));
  window.stopSpeech();
  window.enqueueSpeech('新回复。');
  await new Promise(resolve => setTimeout(resolve, 20));

  assert.deepStrictEqual(fetched, [
    ['/tts/stream', '旧回复。'],
    ['/tts/stream', '新回复。'],
  ]);
  assert.strictEqual(started.length, 1);
  console.log('local_tts streaming barge-in next-turn test passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
