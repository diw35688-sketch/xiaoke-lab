(() => {
  let currentAudio = null, requestController = null, queue = [], running = false, jobId = 0;
  const status = document.querySelector('#voice-status');
  const setStatus = text => { if (status) status.textContent = text; };
  const avatar = state => window.dispatchAvatarState?.(state);
  // 通话模式进行中：回答播完应回到"正在聆听"，而不是归位"准备就绪"。
  function isCallActive() {
    const btn = document.getElementById('sh-call');
    return btn ? btn.classList.contains('active') : false;
  }
  function settleAvatar() {
    avatar(isCallActive() ? 'listening' : 'idle');
  }
  function cleanForSpeech(text) {
    return text.replace(/```[\s\S]*?```/g, '代码内容已省略。').replace(/https?:\/\/\S+/g, '链接')
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, '')
      .replace(/[*_`#>|~]/g, '').replace(/\s+/g, ' ').trim();
  }
  function splitText(text, maxLength = 280) {
    // 只按句末标点（。！？!?）分句；逗号、顿号、分号、冒号留在句内交给 TTS 自然停顿，避免人为切缝。
    const sentences = text.match(/[^。！？!?\n]+[。！？!?]?/g) || [text];
    const result = []; let current = '';
    for (const sentence of sentences) { const part = sentence.trim(); if (!part) continue; if (current && current.length + part.length > maxLength) { result.push(current); current = part; } else current += part; }
    if (current) result.push(current); return result;
  }
  function stopSpeech() {
    jobId += 1; queue = []; requestController?.abort(); currentAudio?.pause(); currentAudio = null; window.speechSynthesis?.cancel(); settleAvatar();
  }
  function play(blob, expectedJob) {
    return new Promise((resolve, reject) => {
      if (expectedJob !== jobId) return resolve();
      const url = URL.createObjectURL(blob); currentAudio = new Audio(url);
      currentAudio.onplay = () => { setStatus('正在朗读回复…'); avatar('speaking'); };
      currentAudio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; resolve(); };
      currentAudio.onerror = () => { URL.revokeObjectURL(url); currentAudio = null; reject(new Error('浏览器播放音频失败')); };
      currentAudio.play().catch(reject);
    });
  }
  // 浏览器内置合成兜底：/tts 不可用时仍能出声，保证"说出来"这个能力不丢。
  function browserFallback(text) {
    if (!window.speechSynthesis) return false;
    try {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'zh-CN'; utterance.rate = 1.05;
      window.speechSynthesis.speak(utterance);
      return true;
    } catch (e) { return false; }
  }
  async function processQueue(expectedJob) {
    if (running) return; running = true;
    try {
      while (queue.length && expectedJob === jobId) {
        const text = queue.shift();
        try {
          requestController = new AbortController(); setStatus('正在生成下一句语音…');
          const response = await fetch('/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal: requestController.signal });
          if (!response.ok) {
            let detail = '语音生成失败';
            try { const err = await response.json(); if (err && err.detail) detail = err.detail; } catch (e) { /* 非 JSON 错误体 */ }
            throw new Error(detail);
          }
          await play(await response.blob(), expectedJob);
        } catch (error) {
          if (error.name === 'AbortError' || expectedJob !== jobId) break;
          if (!browserFallback(text)) setStatus('本地语音失败：' + error.message);
        }
      }
      if (expectedJob === jobId) { setStatus(isCallActive() ? '正在聆听，请说话' : '朗读完成'); settleAvatar(); }
    } catch (error) { if (error.name !== 'AbortError' && expectedJob === jobId) { setStatus(`本地语音失败：${error.message}`); settleAvatar(); } }
    finally { running = false; if (queue.length && expectedJob === jobId) processQueue(expectedJob); }
  }
  function addToQueue(text, replace) {
    if (window.ttsMuted === true) return; // 头像开关已关闭语音播报
    if (replace) stopSpeech(); const clean = cleanForSpeech(text); if (!clean) return; const expectedJob = jobId; queue.push(...splitText(clean)); processQueue(expectedJob);
  }
  window.stopSpeech = stopSpeech; window.speak = text => addToQueue(text, true); window.enqueueSpeech = text => addToQueue(text, false);
})();
