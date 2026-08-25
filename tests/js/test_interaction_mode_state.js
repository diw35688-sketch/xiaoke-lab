const assert = require('assert');

global.window = {};
require('../../web/frontend/interaction_mode_state.js');

const state = window.createInteractionModeState();
assert.deepStrictEqual(state.capture('text'), {
  interaction_mode: 'chat', experiment_context: 'none', mode_version: 1, input_source: 'text',
});

state.select('free');
const submitted = state.capture('single_recording');
assert.deepStrictEqual(submitted, {
  interaction_mode: 'experiment', experiment_context: 'free', mode_version: 2,
  input_source: 'single_recording',
});
state.select('protocol');
assert.strictEqual(submitted.experiment_context, 'free');
assert.strictEqual(submitted.mode_version, 2);
assert.strictEqual(state.capture('continuous_call').mode_version, 3);
state.select('protocol');
assert.strictEqual(state.current().mode_version, 3);

const form = {};
window.interactionModeState.select('free');
const queued = window.captureComposerModeSnapshot(form, 'text');
window.interactionModeState.select('protocol');
assert.strictEqual(window.consumeComposerModeSnapshot(form, 'text'), queued);
assert.strictEqual(window.consumeComposerModeSnapshot(form, 'text').experiment_context, 'protocol');
assert.throws(() => state.select('hidden'), /未知交互模式/);
assert.throws(() => state.capture('microphone'), /未知输入来源/);

console.log('interaction_mode_state: OK');
