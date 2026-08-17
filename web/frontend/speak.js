// 语音播报：优先用本机 Qwen3-TTS（音色好），不可用时自动回退浏览器内置合成。
// 产品要求：追问和安全提示必须能"说出来"，因为学生双手在忙、看不见屏幕。
(function () {
  var localAvailable = null;   // null=未知, true/false=已探测
  var audio = null;

  function browserSpeak(text) {
    if (!window.speechSynthesis) return false;
    try {
      window.speechSynthesis.cancel();
      var utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'zh-CN';
      utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
      return true;
    } catch (e) { return false; }
  }

  function stop() {
    if (audio) { try { audio.pause(); } catch (e) {} audio = null; }
    if (window.speechSynthesis) { try { window.speechSynthesis.cancel(); } catch (e) {} }
  }

  function speak(text) {
    if (!text) return Promise.resolve(false);
    if (window.ttsMuted === true) return Promise.resolve(false); // 头像开关已关闭语音播报
    stop();
    if (localAvailable === false) return Promise.resolve(browserSpeak(text));

    return fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text })
    }).then(function (r) {
      if (!r.ok) throw new Error('local tts unavailable');
      return r.blob();
    }).then(function (blob) {
      localAvailable = true;
      audio = new Audio(URL.createObjectURL(blob));
      audio.play();
      return true;
    }).catch(function () {
      localAvailable = false;
      return browserSpeak(text);
    });
  }

  window.labSpeak = speak;
  window.labSpeakStop = stop;
})();
