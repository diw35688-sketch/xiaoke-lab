(() => {
  let currentAudio = null, requestController = null, queue = [], running = false, jobId = 0;
  const status = document.querySelector('#voice-status');
  const avatar = state => window.dispatchAvatarState?.(state);
  function cleanForSpeech(text) {
    return text.replace(/```[\s\S]*?```/g, '代码内容已省略。').replace(/https?:\/\/\S+/g, '链接')
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, '')
      .replace(/[*_`#>|~]/g, '').replace(/\s+/g, ' ').trim();
  }
  function splitText(text, maxLength = 70) {
    const sentences = text.match(/[^。！？!?；;：:,，\n]+[。！？!?；;：:,，\n]?/g) || [text];
    const result = []; let current = '';
    for (const sentence of sentences) { const part = sentence.trim(); if (!part) continue; if (current && current.length + part.length > maxLength) { result.push(current); current = part; } else current += part; }
    if (current) result.push(current); return result;
  }
  function stopSpeech() {
    jobId += 1; queue = []; requestController?.abort(); currentAudio?.pause(); currentAudio = null; window.speechSynthesis?.cancel(); avatar('idle');
  }
  function play(blob, expectedJob) {
    return new Promise((resolve, reject) => {
      if (expectedJob !== jobId) return resolve();
      const url = URL.createObjectURL(blob); currentAudio = new Audio(url);
      currentAudio.onplay = () => { status.textContent = '正在朗读回复…'; avatar('speaking'); };
      currentAudio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; resolve(); };
      currentAudio.onerror = () => { URL.revokeObjectURL(url); currentAudio = null; reject(new Error('浏览器播放音频失败')); };
      currentAudio.play().catch(reject);
    });
  }
  async function processQueue(expectedJob) {
    if (running) return; running = true;
    try {
      while (queue.length && expectedJob === jobId) {
        const text = queue.shift(); requestController = new AbortController(); status.textContent = '正在生成下一句语音…';
        const response = await fetch('/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal: requestController.signal });
        const error = response.ok ? null : await response.json(); if (!response.ok) throw new Error(error.detail || '语音生成失败');
        await play(await response.blob(), expectedJob);
      }
      if (expectedJob === jobId) { status.textContent = '朗读完成'; avatar('idle'); }
    } catch (error) { if (error.name !== 'AbortError' && expectedJob === jobId) { status.textContent = `本地语音失败：${error.message}`; avatar('idle'); } }
    finally { running = false; if (queue.length && expectedJob === jobId) processQueue(expectedJob); }
  }
  function addToQueue(text, replace) { if (replace) stopSpeech(); const clean = cleanForSpeech(text); if (!clean) return; const expectedJob = jobId; queue.push(...splitText(clean)); processQueue(expectedJob); }
  window.stopSpeech = stopSpeech; window.speak = text => addToQueue(text, true); window.enqueueSpeech = text => addToQueue(text, false);
})();
