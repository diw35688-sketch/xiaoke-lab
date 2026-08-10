(() => {
  const form = document.querySelector('#form'), input = document.querySelector('#message'), send = document.querySelector('#send'), mic = document.querySelector('#mic'), chat = document.querySelector('#chat'), autoSpeak = document.querySelector('#auto-speak'), conversationKey = 'lab-agent-conversation-id';
  const avatar = state => window.dispatchAvatarState?.(state);
  let activeController = null, activeReply = null, requestId = 0;
  const stopButton = document.createElement('button'); stopButton.type = 'button'; stopButton.className = 'mic'; stopButton.id = 'stop-response'; stopButton.title = '停止生成'; stopButton.textContent = '■'; stopButton.disabled = true; send.after(stopButton);
  function add(text, role) { const row = document.createElement('div'), bubble = document.createElement('div'); row.className = `message ${role}`; bubble.className = 'bubble'; bubble.textContent = text; row.appendChild(bubble); chat.appendChild(row); chat.scrollTop = chat.scrollHeight; return bubble; }
  window.addChatMessage = add;
  window.isAssistantBusy = () => Boolean(activeController);
  function takeCompletedSentences(buffer, flush = false) { const sentences = []; let match; while ((match = buffer.match(/^([\s\S]*?[。！？!?；;：:,，\n])/))) { sentences.push(match[1]); buffer = buffer.slice(match[1].length); } if (flush && buffer.trim()) { sentences.push(buffer); buffer = ''; } return { buffer, sentences }; }
  function stopCurrentResponse(showNotice = true) { if (!activeController) return; activeController.abort(); activeController = null; window.stopSpeech?.(); stopButton.disabled = true; avatar('interrupted'); setTimeout(() => avatar('idle'), 900); if (showNotice && activeReply && activeReply.textContent.trim()) activeReply.textContent += '\n\n[已停止生成]'; }
  window.stopCurrentResponse = stopCurrentResponse; stopButton.onclick = () => stopCurrentResponse();
  const originalMicClick = mic?.onclick; if (mic) mic.onclick = () => { stopCurrentResponse(false); avatar('listening'); originalMicClick?.(); };
  form.onsubmit = async event => {
    event.preventDefault(); const message = input.value.trim(); if (!message) return; stopCurrentResponse(false); const ownId = ++requestId;
    add(message, 'user'); input.value = ''; const reply = add('正在思考…', 'assistant'); activeReply = reply; activeController = new AbortController(); stopButton.disabled = false; avatar('thinking');
    let answer = '', speechBuffer = '';
    try {
      const response = await fetch('/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, conversation_id: localStorage.getItem(conversationKey) || null }), signal: activeController.signal });
      if (!response.ok || !response.body) throw new Error('无法建立流式回复。');
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); let boundary;
        while ((boundary = buffer.indexOf('\n\n')) >= 0) {
          const rawEvent = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2); const dataLine = rawEvent.split('\n').find(line => line.startsWith('data: ')); if (!dataLine) continue;
          const data = JSON.parse(dataLine.slice(6));
          if (data.type === 'delta') { answer += data.text; reply.textContent = answer; chat.scrollTop = chat.scrollHeight; if (autoSpeak.checked) { const extracted = takeCompletedSentences(speechBuffer + data.text); speechBuffer = extracted.buffer; extracted.sentences.forEach(sentence => window.enqueueSpeech?.(sentence)); } }
          else if (data.type === 'task_queued') { answer = data.answer; reply.textContent = answer; if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id); if (autoSpeak.checked) window.enqueueSpeech?.(answer); avatar('listening'); window.refreshTaskPanel?.(); }
          else if (data.type === 'done') { if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id); if (autoSpeak.checked) { const extracted = takeCompletedSentences(speechBuffer, true); extracted.sentences.forEach(sentence => window.enqueueSpeech?.(sentence)); } else { avatar('happy'); setTimeout(() => avatar('idle'), 1000); } if (typeof loadExperiments === 'function') loadExperiments(); }
          else if (data.type === 'error') throw new Error(data.detail || '流式回复失败');
        }
      }
      if (!answer) reply.textContent = '模型没有返回文字内容。';
    } catch (error) { if (error.name === 'AbortError' || ownId !== requestId) return; reply.textContent = `出错了：${error.message}`; avatar('interrupted'); setTimeout(() => avatar('idle'), 900); }
    finally { if (ownId === requestId) { activeController = null; activeReply = null; stopButton.disabled = true; input.focus(); } }
  };
})();
