const assert = require('assert');
const {normalizeWakeText, detectWakeWord} = require('../../web/frontend/wake_word.js');

assert.strictEqual(normalizeWakeText(' 小科，小科！ '), '小科小科');
assert.strictEqual(detectWakeWord('小科，小科。'), '小科小科');
assert.strictEqual(detectWakeWord('你好，小科！'), '小科小科');
assert.strictEqual(detectWakeWord('小科小科，请开始记录'), '小科小科');
assert.strictEqual(detectWakeWord('小可小可'), '小科小科');
assert.strictEqual(detectWakeWord('小柯小柯'), '小科小科');
assert.strictEqual(detectWakeWord('小科'), '小科小科');
assert.strictEqual(detectWakeWord('小科实验需要多少盐'), null);
assert.strictEqual(detectWakeWord('今天做实验'), null);
assert.strictEqual(detectWakeWord('', ['测试唤醒']), null);

console.log('wake_word: OK');
