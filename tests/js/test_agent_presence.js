// 小科状态条行为测试：三个既有事件源驱动，词表与立绘一致，失败才转警示。
const assert = require('assert');

const windowListeners = {};
const documentListeners = {};

function makeNode() {
  return {
    id: '', className: '', textContent: '', innerHTML: '',
    style: {display: ''},
    children: {},
    querySelector(sel) { return this.children[sel] || null; },
  };
}

// 状态条挂载后的三个子节点
const stateNode = makeNode();
const extraNode = makeNode();
const presence = makeNode();
presence.children['.ap-state'] = stateNode;
presence.children['.ap-extra'] = extraNode;

// 聊天头部：第一个 span 是标题槽位
const slot = makeNode();
const head = makeNode();
head.querySelector = sel => (sel === 'span' ? slot : null);

let mounted = false;
global.document = {
  readyState: 'complete',
  getElementById(id) {
    if (id === 'sh-chat-head') return head;
    if (id === 'agent-presence') return mounted ? presence : null;
    return null;
  },
  addEventListener(type, fn) { documentListeners[type] = fn; },
};
global.window = {
  addEventListener(type, fn) { windowListeners[type] = fn; },
};

require('../../web/frontend/agent_presence.js');

// 模块加载即挂载（readyState=complete）：标题槽位被替换为状态条
assert.ok(slot.innerHTML.includes('agent-presence'));
assert.ok(slot.innerHTML.includes('小科'));
mounted = true;

// 立绘状态词表一致：listening → 正在聆听 + 「直接说话」提示
windowListeners['avatar-state']({detail: {state: 'listening'}});
assert.strictEqual(stateNode.textContent, '正在聆听');
assert.strictEqual(presence.className, 'ap-listening');
// 语音栈尚未就绪（0/4）时提示准备进度而不是「直接说话」
assert.strictEqual(extraNode.textContent, '语音准备中 0/4');

// 四个组件全部就绪 → 进度提示消失，回到状态提示
['tts_warmup', 'silero_assets', 'microphone', 'asr_warmup'].forEach(component => {
  windowListeners['lab:voice-startup-progress']({detail: {component, state: 'ready'}});
});
assert.strictEqual(extraNode.textContent, '直接说话');

// 通话中回答 → 「说话可打断」；挂断后提示消失
documentListeners['lab:continuous-call-state']({detail: {active: true}});
windowListeners['avatar-state']({detail: {state: 'speaking'}});
assert.strictEqual(stateNode.textContent, '正在回答');
assert.strictEqual(extraNode.textContent, '说话可打断');
documentListeners['lab:continuous-call-state']({detail: {active: false}});
assert.strictEqual(extraNode.style.display, 'none');

// 某组件失败 → 警示样式 + 「语音部分不可用」，任何状态下持续可见
windowListeners['lab:voice-startup-progress']({detail: {component: 'microphone', state: 'error', detail: '权限被拒绝'}});
assert.ok(presence.className.includes('ap-warn'));
assert.strictEqual(extraNode.textContent, '语音部分不可用');

// 未知状态不崩溃、不改词表
windowListeners['avatar-state']({detail: {state: 'unknown-state'}});
assert.strictEqual(stateNode.textContent, '正在回答');

console.log('agent_presence: OK');
