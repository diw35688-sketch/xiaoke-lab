const assert = require('assert');

global.window = {};
require('../../web/frontend/interaction_mode_state.js');

const state = window.createInteractionModeState();
assert.deepStrictEqual(state.capture('text'), {
  interaction_mode: 'chat', experiment_context: 'none', mode_version: 1, input_source: 'text',
  protocol_id: null,
});

state.select('free');
const submitted = state.capture('single_recording');
assert.deepStrictEqual(submitted, {
  interaction_mode: 'experiment', experiment_context: 'free', mode_version: 2,
  input_source: 'single_recording',
  protocol_id: null,
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

window.interactionModeState = window.createInteractionModeState();
window.applyInteractionModeUiAction({
  type: 'switch_interaction_mode', mode: 'free', view: 'run',
});
assert.deepStrictEqual(window.interactionModeState.capture('text'), {
  interaction_mode: 'experiment', experiment_context: 'free', mode_version: 2,
  input_source: 'text', protocol_id: null,
});
window.applyInteractionModeUiAction({
  type: 'switch_interaction_mode', mode: 'protocol', protocol_id: 'p-1', view: 'run',
});
assert.deepStrictEqual(window.interactionModeState.capture('continuous_call'), {
  interaction_mode: 'experiment', experiment_context: 'protocol', mode_version: 3,
  input_source: 'continuous_call', protocol_id: 'p-1',
});
assert.throws(
  () => window.applyInteractionModeUiAction({type: 'switch_interaction_mode', mode: 'protocol'}),
  /protocol_id/
);
assert.throws(() => state.select('hidden'), /未知交互模式/);
assert.throws(() => state.capture('microphone'), /未知输入来源/);

console.log('interaction_mode_state: OK');
