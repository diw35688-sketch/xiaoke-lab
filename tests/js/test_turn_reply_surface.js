const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const context = {window: {}};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync(
    path.join(__dirname, '../../web/frontend/turn_reply_surface.js'),
    'utf8'
  ),
  context
);

let removed = false;
let published = null;
const row = {
  classList: {contains: name => name === 'message'},
  remove: () => { removed = true; },
};
const reply = {parentElement: row};

const cardResult = context.window.settleTurnReplySurface({
  reply,
  assistant: {payload: {text: '已补充完整', presentation: 'clarification_card'}},
  publishAnswer: text => { published = text; },
});
assert.strictEqual(cardResult, 'card');
assert.strictEqual(removed, true);
assert.strictEqual(published, null);

removed = false;
const textResult = context.window.settleTurnReplySurface({
  reply,
  assistant: {payload: {text: '实验记录已保存'}},
  publishAnswer: text => { published = text; },
});
assert.strictEqual(textResult, 'text');
assert.strictEqual(removed, false);
assert.strictEqual(published, '实验记录已保存');

console.log('turn_reply_surface: OK');
