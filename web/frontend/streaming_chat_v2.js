// 对话流 v2：回答、思考链、工具调用链都在右侧对话框内可见。
// - [[LABTHINK]] 渲染为可折叠的“思考过程”行（同时同步到 Live2D 气泡）。
// - [[LABCARD]] 渲染为紧凑的“工具调用”行，并继续转发到中间画布。
// - 普通 delta 仍是 assistant 文本，不混入任何标记。
(() => {
  const $ = id => document.getElementById(id);
  const form = $('form'), input = $('message'), send = $('send'), mic = $('mic'), chat = $('chat'),
        autoSpeak = $('auto-speak'), conversationKey = 'lab-agent-conversation-id';
  const avatar = state => window.dispatchAvatarState?.(state);
  let activeController = null, activeReply = null, requestId = 0;
  let activeThinkRow = null, toolRows = {};

  // 朗读开关统一来源：通话模式强制勾选的 #auto-speak，或设置面板的 tts_enabled（后端）。
  // 页面加载时读后端配置，避免"设置里开了播报、对话却不朗读"的断链。
  window.ttsEnabled = window.ttsEnabled === true;
  fetch('/settings').then(r => r.json()).then(d => {
    window.ttsEnabled = !!(d.settings && d.settings.tts_enabled);
  }).catch(() => {});
  function shouldSpeak() { return autoSpeak.checked || window.ttsEnabled === true; }

  const stopButton = document.createElement('button');
  stopButton.type = 'button'; stopButton.className = 'mic'; stopButton.id = 'stop-response';
  stopButton.title = '停止生成'; stopButton.textContent = '■'; stopButton.disabled = true;
  send.after(stopButton);

  function add(text, role) {
    const row = document.createElement('div'), bubble = document.createElement('div');
    row.className = `message ${role}`; bubble.className = 'bubble'; bubble.textContent = text;
    row.appendChild(bubble); chat.appendChild(row); chat.scrollTop = chat.scrollHeight; return bubble;
  }
  window.addChatMessage = add;
  window.isAssistantBusy = () => Boolean(activeController);

  function lastLine(text) {
    const visible = String(text || '').trimEnd();
    const index = visible.lastIndexOf('\n');
    return index === -1 ? visible : visible.slice(index + 1);
  }

  function avatarThought(text) {
    const el = document.querySelector('.avatar-thought');
    if (el) el.textContent = text || '···';
  }

  function messageRow(reply) {
    // add() 返回的是气泡节点；插入思考/工具行时要插到整条消息前面，
    // 因此定位到气泡所属的 .message 行。
    return reply && reply.parentElement && reply.parentElement.classList.contains('message')
      ? reply.parentElement
      : reply;
  }

  function ensureThinkRow(reply) {
    if (activeThinkRow) return activeThinkRow;
    const row = document.createElement('div');
    row.className = 'message think running';
    row.innerHTML = '<div class="chat-think"><div class="chat-think-head"><span class="ic">☰</span><span class="tt">思考过程</span><span class="st">进行中</span></div><div class="chat-think-body"></div></div>';
    chat.insertBefore(row, messageRow(reply));
    activeThinkRow = row;
    return row;
  }

  function updateThink(reply, text, running) {
    const row = ensureThinkRow(reply);
    const body = row.querySelector('.chat-think-body');
    body.textContent = running ? lastLine(text) : (text || '').trim();
    body.scrollTop = body.scrollHeight;
    const st = row.querySelector('.chat-think-head .st');
    if (st) st.textContent = running ? '进行中' : '已完成';
    row.classList.toggle('running', Boolean(running));
    row.classList.toggle('done', !running);
    avatarThought(running ? lastLine(text) : '···');
    chat.scrollTop = chat.scrollHeight;
  }

  function ensureToolRow(view, reply) {
    let row = toolRows[view.title];
    if (!row) {
      row = document.createElement('div');
      row.className = 'message tool';
      row.innerHTML = '<div class="chat-tool"><div class="chat-tool-head"><span class="ic">⚙</span><span class="tt"></span><span class="st">进行中</span></div><div class="chat-tool-body"></div></div>';
      chat.insertBefore(row, messageRow(reply));
      toolRows[view.title] = row;
    }
    const state = view.status === 'pending' ? '进行中' : (view.status === 'error' ? '失败' : '完成');
    const lines = (view.lines || []).filter(Boolean).slice(0, 4);
    row.querySelector('.chat-tool-head .tt').textContent = view.title || '工具调用';
    const st = row.querySelector('.chat-tool-head .st');
    st.textContent = state; st.className = 'st ' + (view.status || 'done');
    row.querySelector('.chat-tool-body').textContent = lines.join('\n');
    row.classList.toggle('tool-error', view.status === 'error');
    chat.scrollTop = chat.scrollHeight;
  }

  window.chatPushThink = (text, running) => { if (activeReply) updateThink(activeReply, text, running); };
  window.chatPushTool = view => { if (activeReply) ensureToolRow(view, activeReply); };

  const WELCOME_TEXT = '你好！我是实验助手。你可以让我记录实验口述、查询试剂安全、推进实验步骤，或安排实验。';

  function clearChat() {
    chat.textContent = '';
    add(WELCOME_TEXT, 'assistant');
  }

  function loadHistory() {
    const id = localStorage.getItem(conversationKey);
    const url = id
      ? `/chat/history?conversation_id=${encodeURIComponent(id)}`
      : '/chat/history';
    fetch(url).then(response => {
      if (!response.ok) throw new Error('读取对话历史失败');
      return response.json();
    }).then(data => {
      if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
      const messages = data.messages || [];
      if (!messages.length) return;   // 没有历史时保留初始欢迎语
      chat.textContent = '';
      messages.forEach(item => {
          const clean = String(item.content || '').replace(/\[\[LABTHINK\]\]|\[\[LABCARD\]\]/g, '');
          add(clean, item.role === 'user' ? 'user' : 'assistant');
        });
    }).catch(() => {
      /* 服务端没有历史或接口失败时，保留当前欢迎语即可。 */
    });
  }

    document.addEventListener('click', event => {
      const phone = event.target.closest('#sh-phone');
      if (!phone) return;
      window.open('/phone', '_blank');
    });


  document.addEventListener('click', event => {
    const button = event.target.closest('#sh-new-chat');
    if (!button) return;
    localStorage.removeItem(conversationKey);
    activeThinkRow = null; toolRows = {};
    window.runClearStream?.();
    clearChat();
  });

  loadHistory();


  function takeCompletedSentences(buffer, flush = false) {
    const sentences = []; let match;
    while ((match = buffer.match(/^([\s\S]*?[。！？!?；;：:,，\n])/))) { sentences.push(match[1]); buffer = buffer.slice(match[1].length); }
    if (flush && buffer.trim()) { sentences.push(buffer); buffer = ''; }
    return { buffer, sentences };
  }

  function stopCurrentResponse(showNotice = true) {
    if (!activeController) return;
    activeController.abort(); activeController = null;
    window.stopSpeech?.(); stopButton.disabled = true;
    avatar('interrupted'); setTimeout(() => avatar('idle'), 900);
    if (showNotice && activeReply && activeReply.textContent.trim()) activeReply.textContent += '\n\n[已停止生成]';
  }
  window.stopCurrentResponse = stopCurrentResponse;
  stopButton.onclick = () => stopCurrentResponse();

  const originalMicClick = mic?.onclick;
  if (mic) mic.onclick = () => { stopCurrentResponse(false); avatar('listening'); originalMicClick?.(); };

  form.onsubmit = async event => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    stopCurrentResponse(false);
    const ownId = ++requestId;

    window.runClearStream?.();
    activeThinkRow = null; toolRows = {};
    add(message, 'user');
    input.value = '';
    const reply = add('正在思考…', 'assistant');
    activeReply = reply;
    activeController = new AbortController();
    stopButton.disabled = false;
    avatar('thinking');

    let answer = '', speechBuffer = '';
    try {
      const response = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation_id: localStorage.getItem(conversationKey) || null }),
        signal: activeController.signal,
      });
      if (!response.ok || !response.body) throw new Error('无法建立流式回复。');
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let buffer = '', thinkBuffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) >= 0) {
          const rawEvent = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
          const dataLine = rawEvent.split('\n').find(line => line.startsWith('data: '));
          if (!dataLine) continue;
          const data = JSON.parse(dataLine.slice(6));

          if (data.type === 'delta' && data.text) {
            const text = data.text;
            if (text.indexOf('[[LABTHINK]]') >= 0) {
              const parts = text.split('[[LABTHINK]]');
              answer += parts[0];
              thinkBuffer += parts.slice(1).join('');
              window.chatPushThink(thinkBuffer, true);
              window.runPushThink?.(thinkBuffer, true);
              reply.textContent = answer;
              chat.scrollTop = chat.scrollHeight;
              continue;
            }
            if (text.indexOf('[[LABCARD]]') >= 0) {
              const parts = text.split('[[LABCARD]]');
              answer += parts[0];
              for (let i = 1; i < parts.length; i++) {
                try {
                  const view = JSON.parse(parts[i]);
                  window.chatPushTool(view);
                  window.labToolCard?.(view);
                } catch (e) { answer += parts[i]; }
              }
              reply.textContent = answer;
              chat.scrollTop = chat.scrollHeight;
              continue;
            }
            answer += text;
            reply.textContent = answer;
            chat.scrollTop = chat.scrollHeight;
            if (shouldSpeak()) {
              const extracted = takeCompletedSentences(speechBuffer + text);
              speechBuffer = extracted.buffer;
              extracted.sentences.forEach(sentence => window.enqueueSpeech?.(sentence));
            }
          } else if (data.type === 'task_queued') {
            answer = data.answer; reply.textContent = answer;
            if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
            if (shouldSpeak()) window.enqueueSpeech?.(answer);
            avatar('listening');
            window.refreshTaskPanel?.();
          } else if (data.type === 'done') {
            if (thinkBuffer) {
              window.chatPushThink(thinkBuffer, false);
              window.runPushThink?.(thinkBuffer, false);
            } else {
              avatarThought('···');
            }
            if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
            if (shouldSpeak()) {
              const extracted = takeCompletedSentences(speechBuffer, true);
              extracted.sentences.forEach(sentence => window.enqueueSpeech?.(sentence));
            } else {
              avatar('happy'); setTimeout(() => avatar('idle'), 1000);
            }
            if (typeof loadExperiments === 'function') loadExperiments();
          } else if (data.type === 'error') {
            throw new Error(data.detail || '流式回复失败');
          }
        }
      }
      if (!answer) reply.textContent = '模型没有返回文字内容。';
    } catch (error) {
      if (error.name === 'AbortError' || ownId !== requestId) return;
      reply.textContent = `出错了：${error.message}`;
      avatar('interrupted'); setTimeout(() => avatar('idle'), 900);
    } finally {
      if (ownId === requestId) { activeController = null; activeReply = null; stopButton.disabled = true; input.focus(); }
    }
  };
})();
