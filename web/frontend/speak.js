// 语音播报的"薄适配层"：三张嘴已收敛为单一 window.speak（见 local_tts.js）。
// 本文件只保留 labSpeak / labSpeakStop / labSpeakMessages 这三个外部名字的兼容，
// 实际发声一律委托给 local_tts.js 的 window.speak / window.stopSpeech，
// 保证打断（stopSpeech）能停住同一张嘴，不再有第二套 Audio 停不到。
(function () {
  window.labSpeak = function (text) {
    return window.speak ? window.speak(text) : false;
  };
  window.labSpeakStop = function () {
    if (window.stopSpeech) window.stopSpeech();
  };

  // 朗读 messages 中需要播报的（追问优先，一次一条）。判断逻辑保留在此，
  // 但发声委托 window.speak——前端仍不判"要不要问"，只认 screen_target/kind。
  window.labSpeakMessages = function (msgs) {
    if (!msgs || !msgs.length) return;
    var speakable = msgs.filter(function (m) { return Boolean(m.voice_text); });
    if (speakable.length) {
      // 词在后端：直接念 copy 层给的 voice_text（已去"小科："前缀），前端不再剥。
      window.labSpeak(String(speakable[0].voice_text));
    }
  };
})();
