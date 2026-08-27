const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const context = {
  window: {},
  document: {
    head: {appendChild() {}},
    createElement: () => ({textContent: ''}),
  },
};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync(
    path.join(__dirname, '../../web/frontend/record_ledger_view.js'), 'utf8'
  ),
  context
);

const html = context.window.renderExperimentLedger({
  session_id: 'lab-1',
  revision: 7,
  count: 1,
  protocol: {
    current_step_number: 2,
    step_statuses: {'1': 'completed', '2': 'in_progress'},
  },
  clarifications: [{
    display_number: 1,
    protocol_step_number: 1,
    status: 'resolved',
    question: '保存条件是什么？',
    missing_fields: [],
    answers: [{
      raw_text: '室温保存',
      written_fields: [{field: 'condition', value: '室温'}],
    }],
  }],
  items: [{
    segment_id: 1,
    transcript: '溶液透明',
    entities: {observation: '溶液透明'},
    evaluation: {deviations: [{
      field: 'amount_value', protocol_value: '3.58', actual_value: '3.5',
    }]},
    step: {step: {number: 1}},
    at: '2026-08-27',
  }],
});

assert.ok(html.includes('步骤 1'));
assert.ok(html.includes('已完成'));
assert.ok(html.includes('步骤 2（当前）'));
assert.ok(html.includes('问题 1'));
assert.ok(html.includes('已解决'));
assert.ok(html.includes('补充答案'));
assert.ok(html.includes('用户答了'));
assert.ok(html.includes('室温保存'));
assert.ok(html.includes('最终写入'));
assert.ok(html.includes('实验条件=室温'));
assert.ok(html.includes('溶液透明'));
assert.ok(html.includes('偏差：体积或质量数值'));
assert.ok(html.includes('期望：3.58'));
assert.ok(html.includes('实际：3.5'));
console.log('record_ledger_view: OK');
