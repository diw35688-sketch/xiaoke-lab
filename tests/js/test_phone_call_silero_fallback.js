const assert = require('assert');

const wait = (ms = 10) => new Promise(resolve => setTimeout(resolve, ms));
let getUserMediaCalls = 0;
let sileroStarts = 0;
let sileroStops = 0;
let sileroCreates = 0;
let rejectSilero = false;
let sileroCallbacks = null;
const fetchCalls = [];

const classNames = new Set();
const autoSpeak = {checked: false};
const micButton = {
  disabled: false,
  textContent: '◉',
  classList: {
    toggle(name, enabled) { if (enabled) classNames.add(name); else classNames.delete(name); },
  },
};
const status = {textContent: ''};

global.document = {
  readyState: 'complete',
  querySelector(selector) {
    return {
      '#auto-speak': autoSpeak,
      '#cp-mic': micButton,
      '#voice-status': status,
      '#cp-hint': null,
    }[selector] || null;
  },
  addEventListener() {},
  dispatchEvent() {},
};
global.CustomEvent = function (type, options) { this.type = type; this.detail = options.detail; };
Object.defineProperty(global, 'navigator', {
  configurable: true,
  value: {
    mediaDevices: {
      async getUserMedia() {
        getUserMediaCalls += 1;
        return {getTracks() { return [{stop() {}}]; }};
      },
    },
  },
});
class FakeAudioContext {
  constructor() { this.sampleRate = 48000; this.destination = {}; }
  createMediaStreamSource() { return {connect() {}, disconnect() {}}; }
  createScriptProcessor() { return {connect() {}, disconnect() {}, onaudioprocess: null}; }
  createGain() { return {gain: {value: 1}, connect() {}, disconnect() {}}; }
  close() {}
}
global.localStorage = {
  getItem(key) { return key === 'lab-agent-conversation-id' ? 'conversation-a' : null; },
};
global.fetch = async (url, options = {}) => {
  fetchCalls.push({url, options});
  return {ok: true, async json() { return url === '/asr/status' ? {loaded: true} : {}; }};
};
global.FormData = class { append() {} };
global.Blob = class {};
global.window = global;
global.window.AudioContext = FakeAudioContext;
global.window.stopSpeech = () => {};
global.window.createCallSileroVad = async callbacks => {
  sileroCreates += 1;
  if (rejectSilero) throw new Error('model load failed');
  sileroCallbacks = callbacks;
  return {
    start() { sileroStarts += 1; },
    stop() { sileroStops += 1; },
  };
};

require('../../web/frontend/phone_call.js');

(async () => {
  // 页面加载后立即申请权限并创建 Silero，尚不开始提交语音。
  await wait();
  assert.strictEqual(sileroCreates, 1);
  assert.strictEqual(sileroStarts, 0);
  assert.strictEqual(getUserMediaCalls, 0);

  // Silero 是正常主路径：不能再额外申请 RMS 麦克风。
  window.phoneCallToggle();
  await wait();
  assert.strictEqual(sileroStarts, 1);
  assert.strictEqual(getUserMediaCalls, 0);
  assert.strictEqual(micButton.textContent, '■');
  assert.ok(classNames.has('rec'));
  assert.ok(status.textContent.includes('Silero'));

  sileroCallbacks.onEvent('speech_started');
  await wait();
  const speechStartCall = fetchCalls.find(call => call.url === '/voice/runtime/event');
  assert.ok(speechStartCall, 'speech_started should reach the voice runtime endpoint');
  assert.deepStrictEqual(JSON.parse(speechStartCall.options.body), {
    conversation_id: 'conversation-a',
    type: 'user_speech_started',
  });

  sileroCallbacks.onEvent('speech_paused');
  await wait();
  const speechPauseCall = fetchCalls.find(call => {
    if (call.url !== '/voice/runtime/event') return false;
    return JSON.parse(call.options.body).type === 'user_speech_paused';
  });
  assert.ok(speechPauseCall, 'speech_paused should reach the voice runtime endpoint');
  assert.deepStrictEqual(JSON.parse(speechPauseCall.options.body), {
    conversation_id: 'conversation-a',
    type: 'user_speech_paused',
  });

  sileroCallbacks.onEvent('speech_resumed');
  await wait();
  const speechResumeCall = fetchCalls.find(call => {
    if (call.url !== '/voice/runtime/event') return false;
    return JSON.parse(call.options.body).type === 'user_speech_resumed';
  });
  assert.ok(speechResumeCall, 'speech_resumed should reach the voice runtime endpoint');
  assert.deepStrictEqual(JSON.parse(speechResumeCall.options.body), {
    conversation_id: 'conversation-a',
    type: 'user_speech_resumed',
  });

  sileroCallbacks.onEvent('speech_paused');
  sileroCallbacks.onEvent('segment_finalized', new Float32Array(16000));
  await wait(50);
  const runtimeTypes = fetchCalls
    .filter(call => call.url === '/voice/runtime/event')
    .map(call => JSON.parse(call.options.body).type);
  const finalizedIndex = runtimeTypes.lastIndexOf('segment_finalized');
  const asrStartedIndex = runtimeTypes.lastIndexOf('asr_processing_started');
  const asrFinishedIndex = runtimeTypes.lastIndexOf('asr_processing_finished');
  assert.ok(finalizedIndex >= 0, 'segment_finalized should reach the runtime endpoint');
  assert.ok(asrStartedIndex > finalizedIndex, 'ASR must start after segment finalization');
  assert.ok(asrFinishedIndex > asrStartedIndex, 'ASR finish must follow ASR start');

  // 运行中失败：先停 Silero，再启动且只启动一套 RMS 麦克风。
  sileroCallbacks.onFailure(new Error('runtime inference failed'));
  await wait();
  assert.strictEqual(sileroStops, 1);
  assert.strictEqual(getUserMediaCalls, 1);
  assert.ok(status.textContent.includes('基础降噪模式'));

  window.phoneCallToggle();
  await wait();
  assert.strictEqual(sileroStops, 1);

  // 挂断后可重新开始；Silero 初始化失败时再启动一套新的 RMS 链。
  rejectSilero = true;
  window.phoneCallToggle();
  await wait();
  assert.strictEqual(getUserMediaCalls, 2);
  assert.strictEqual(micButton.textContent, '■');
  assert.ok(status.textContent.includes('基础降噪模式'));

  window.phoneCallToggle();
  console.log('phone_call_silero_fallback: OK');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
