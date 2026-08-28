// 唯一交互模式状态源。模式决定业务语义；input_source 只在提交时加入快照。
(function () {
  var MODES = {
    chat: {interaction_mode: 'chat', experiment_context: 'none'},
    free: {interaction_mode: 'experiment', experiment_context: 'free'},
    protocol: {interaction_mode: 'experiment', experiment_context: 'protocol'},
    template: {interaction_mode: 'experiment', experiment_context: 'template'}
  };
  var SOURCES = ['text', 'single_recording', 'continuous_call'];

  function createInteractionModeState() {
    var selected = 'chat';
    var protocolId = null;
    var version = 1;
    var listeners = [];

    function current() {
      return Object.freeze({
        interaction_mode: MODES[selected].interaction_mode,
        experiment_context: MODES[selected].experiment_context,
        mode_version: version,
        protocol_id: protocolId
      });
    }
    function select(name, protocolIdValue) {
      if (!MODES[name]) throw new Error('未知交互模式：' + name);
      var nextProtocolId = name === 'protocol' ? (protocolIdValue || null) : null;
      if (name === selected && nextProtocolId === protocolId) return current();
      selected = name;
      protocolId = nextProtocolId;
      version += 1;
      var value = current();
      listeners.slice().forEach(function (listener) { listener(value); });
      return value;
    }
    function capture(inputSource) {
      if (SOURCES.indexOf(inputSource) < 0) throw new Error('未知输入来源：' + inputSource);
      var mode = current();
      return Object.freeze({
        interaction_mode: mode.interaction_mode,
        experiment_context: mode.experiment_context,
        mode_version: mode.mode_version,
        input_source: inputSource,
        protocol_id: mode.protocol_id
      });
    }
    function subscribe(listener) {
      listeners.push(listener);
      listener(current());
      return function () { listeners = listeners.filter(function (item) { return item !== listener; }); };
    }
    return Object.freeze({current: current, select: select, capture: capture, subscribe: subscribe});
  }

  window.createInteractionModeState = createInteractionModeState;
  window.interactionModeState = window.interactionModeState || createInteractionModeState();
  window.captureComposerModeSnapshot = function (form, inputSource, frozenSnapshot) {
    var snapshot = frozenSnapshot || window.interactionModeState.capture(inputSource);
    if (form) form.__interactionModeSnapshot = snapshot;
    return snapshot;
  };
  window.consumeComposerModeSnapshot = function (form, fallbackSource) {
    var snapshot = form && form.__interactionModeSnapshot;
    if (form) delete form.__interactionModeSnapshot;
    return snapshot || window.interactionModeState.capture(fallbackSource);
  };
})();
