// 对话流 v2：回答、思考链、工具调用链都在右侧对话框内可见。
// - [[LABTHINK]] / [[LABCARD]] 先进入唯一 ConversationTurnStore，再由聊天时间线渲染。
// - 普通 delta 仍是 assistant 文本，不混入任何标记。
(() => {
  const $ = id => document.getElementById(id);
  const form = $('form'), input = $('message'), send = $('send'), mic = $('mic'), chat = $('chat'),
        conversationKey = 'lab-agent-conversation-id',
        freshChatKey = 'lab-agent-fresh-chat';
  const avatar = state => window.dispatchAvatarState?.(state);
  let activeController = null, activeReply = null, requestId = 0;
  let activeThinkRow = null, blockRows = {};
  const turnStore = window.conversationTurnStore;
  const blockView = window.conversationBlockView;
  if (!turnStore) throw new Error('ConversationTurnStore 未加载');

  // 朗读开关统一来源：通话模式强制勾选的 #auto-speak，或设置面板的 tts_enabled（后端）。
  // 页面加载时读后端配置，避免"设置里开了播报、对话却不朗读"的断链。
  window.ttsEnabled = window.ttsEnabled === true;
  fetch('/settings').then(r => r.json()).then(d => {
    window.ttsEnabled = !!(d.settings && d.settings.tts_enabled);
  }).catch(() => {});
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

  function settleCommittedReply(reply, assistant, publishAnswer) {
    if (typeof window.settleTurnReplySurface === 'function') {
      return window.settleTurnReplySurface({reply, assistant, publishAnswer});
    }
    if (assistant?.payload?.presentation === 'clarification_card') {
      messageRow(reply)?.remove?.();
      return 'card';
    }
    publishAnswer(assistant?.payload?.text || '处理完成。');
    return 'text';
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

  function ensureToolRow(block, reply) {
    const view = block.payload;
    let row = blockRows[block.block_id];
    if (!row) {
      row = document.createElement('div');
      row.className = 'message tool';
      row.innerHTML = '<div class="chat-tool"><div class="chat-tool-head"><span class="ic">⚙</span><span class="tt"></span><span class="st">进行中</span></div><div class="chat-tool-body"></div></div>';
      chat.insertBefore(row, messageRow(reply));
      blockRows[block.block_id] = row;
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

  function ensureCardRow(block, reply) {
    const view = blockView?.(block);
    if (!view) return;
    let row = blockRows[block.block_id];
    if (!row) {
      row = document.createElement('div');
      row.className = `message block-card tone-${view.tone}`;
      row.dataset.blockId = block.block_id;
      row.innerHTML = '<div class="chat-block"><div class="chat-block-head"><span class="label"></span><span class="title"></span><span class="status"></span></div><div class="chat-block-lines"></div><div class="chat-block-meta"></div></div>';
      chat.insertBefore(row, messageRow(reply) || null);
      blockRows[block.block_id] = row;
    }
    row.className = `message block-card tone-${view.tone}`;
    row.querySelector('.label').textContent = view.label;
    row.querySelector('.title').textContent = view.title;
    row.querySelector('.status').textContent = view.status;
    row.querySelector('.chat-block-lines').textContent = view.lines.join('\n');
    row.querySelector('.chat-block-meta').textContent = view.meta.join(' · ');
    chat.scrollTop = chat.scrollHeight;
  }

  // 单次录音和连续通话不经过文字表单的 activeReply，仍应使用同一张结构化卡片。
  window.addCommittedAssistantSurface = committed => {
    const cards = (committed?.blocks || []).filter(
      block => block.type === 'confirmation_card'
    );
    if (cards.length) {
      cards.forEach(block => ensureCardRow(block, null));
      return;
    }
    const assistant = (committed?.blocks || []).find(
      block => block.type === 'assistant_text'
    );
    if (assistant?.payload?.text) add(assistant.payload.text, 'assistant');
  };

  turnStore.subscribe(turn => {
    if (!turn) return;
    turn.blocks.forEach(block => {
      if (block.type === 'system_status' && block.payload.kind === 'think' && activeReply) {
        updateThink(activeReply, block.payload.text, block.payload.running);
      } else if (block.type === 'tool_card' && activeReply) {
        ensureToolRow(block, activeReply);
      } else if (block.type === 'assistant_text' && activeReply) {
        if (block.payload.presentation === 'clarification_card') {
          const row = messageRow(activeReply);
          if (row) row.hidden = true;
          return;
        }
        activeReply.textContent = block.payload.text || '';
        chat.scrollTop = chat.scrollHeight;
      } else {
        ensureCardRow(block, activeReply);
      }
    });
  });

  const WELCOME_TEXT = '你好！我是实验助手。你可以让我记录实验口述、查询试剂安全、推进实验步骤，或安排实验。';

  function ensureNewChatStyles() {
    if (document.getElementById('new-chat-options-style')) return;
    var style = document.createElement('style');
    style.id = 'new-chat-options-style';
    style.textContent = [
      '.new-chat-options{display:flex;gap:10px;flex-wrap:wrap;padding:6px 0 12px}',
      '.nco-card{flex:1 1 180px;max-width:260px;background:#fff;border:1px solid #e5e8f0;border-radius:14px;padding:12px 14px;cursor:pointer;transition:box-shadow .15s,transform .15s}',
      '.nco-card:hover{box-shadow:0 6px 18px rgba(15,23,42,.08);transform:translateY(-2px)}',
      '.nco-ic{font-size:20px}',
      '.nco-title{font-weight:700;color:#0f172a;margin:4px 0 2px;font-size:14px}',
      '.nco-desc{color:#64748b;font-size:12px;line-height:1.5}',
      '.mode-intro{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:12px 15px;margin:6px 0 12px}',
      '.mi-title{font-weight:700;color:#0f172a;font-size:14px}',
      '.mi-desc{color:#64748b;font-size:12px;line-height:1.6;margin:4px 0 8px}',
      '.mi-actions{display:flex;gap:6px;flex-wrap:wrap}',
      '.mi-btn{padding:5px 10px;border:1px solid #cbd5e1;background:#fff;border-radius:8px;cursor:pointer;font-size:12px;font-family:inherit}',
      '.mi-btn.primary{background:#2563eb;border-color:#2563eb;color:#fff}',
      '.mi-btn.ghost{background:#f8fafc}'
    ].join('\n');
    document.head.appendChild(style);
  }

  function openMode(mode) {
    window.interactionModeState.select(mode === 'free' ? 'free' : mode);
    var opt = chat.querySelector('.new-chat-options');
    if (opt) opt.remove();
    var input = document.getElementById('message');
    if (mode === 'free') {
      // 自由模式留在聊天区，并显示预设提示
      var intro = chat.querySelector('.mode-intro');
      if (intro) intro.remove();
      var div = document.createElement('div');
      div.className = 'mode-intro';
      div.innerHTML = '<div class="mi-title">🧪 自由模式已开启</div>'
        + '<div class="mi-desc">可以自由聊天、记录实验，不绑定方案。说一句即可开始。</div>';
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      if (input) input.focus();
      return;
    }
    if (mode === 'template') {
      // 制作模板：跳转到实验方案页（支持 PDF/图片 OCR 生成规范模板）
      if (window.shellShow) window.shellShow('protocols');
      return;
    }
    if (mode === 'storage') {
      // 制作储存库：跳转到储存库页面
      if (window.shellShow) window.shellShow('storage');
    }
  }

  function showNewChatOptions() {
    ensureNewChatStyles();
    if (chat.querySelector('.new-chat-options')) return;
    var wrap = document.createElement('div');
    wrap.className = 'new-chat-options';
    wrap.innerHTML = [
      '<div class="nco-card" data-mode="free"><div class="nco-ic">🧪</div><div class="nco-title">自由模式</div><div class="nco-desc">记录/聊天，不绑定方案</div></div>',
      '<div class="nco-card" data-mode="template"><div class="nco-ic">📄</div><div class="nco-title">制作模板</div><div class="nco-desc">把配方/方案做成规范模板</div></div>',
      '<div class="nco-card" data-mode="storage"><div class="nco-ic">🗃</div><div class="nco-title">制作储存库</div><div class="nco-desc">登记位置/物品/库存</div></div>'
    ].join('');
    Array.prototype.forEach.call(wrap.querySelectorAll('.nco-card'), function (card) {
      card.onclick = function () {
        openMode(card.getAttribute('data-mode'));
      };
    });
    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
  }

  function clearChat() {
    chat.textContent = '';
    add(WELCOME_TEXT, 'assistant');
    showNewChatOptions();
  }

  function renderTurnHistory(result) {
    const turnData = result?.turn || result || {};
    const blocks = turnData.blocks || result?.blocks || [];
    let reply = null;
    blocks.forEach(block => {
      const payload = block.payload || {};
      if (block.type === 'user_text') {
        add(payload.text || '', 'user');
        return;
      }
      if (block.type === 'assistant_text') {
        if (!reply) reply = add(payload.text || '', 'assistant');
        else if (reply.parentElement) reply.textContent = payload.text || '';
        return;
      }
      if (block.type === 'system_status' && payload.kind === 'think') {
        if (!reply) reply = add('', 'assistant');
        activeThinkRow = null;
        ensureThinkRow(reply);
        updateThink(reply, payload.text || '', Boolean(payload.running));
        activeThinkRow = null;
        return;
      }
      if (block.type === 'tool_card') {
        if (!reply) reply = add('', 'assistant');
        ensureToolRow(block, reply);
        return;
      }
      if (block.type !== 'user_text') {
        if (!reply) reply = add('', 'assistant');
        ensureCardRow(block, reply);
      }
    });
    if (reply && reply.parentElement && !reply.textContent.trim()) {
      // 只有工具/思考卡片的回合保留空白气泡不太好，但保留结构可读
    }
  }

  function loadHistory(conversationId) {
    if (localStorage.getItem(freshChatKey)) {
      localStorage.removeItem(freshChatKey);
      return;
    }
    const id = conversationId || localStorage.getItem(conversationKey);
    if (id) {
      fetch(`/turn/history?conversation_id=${encodeURIComponent(id)}`).then(response => {
        if (!response.ok) throw new Error('读取 Turn 历史失败');
        return response.json();
      }).then(data => {
        const turns = data.turns || [];
        if (!turns.length) return loadFlatHistory(id);
        chat.textContent = '';
        add(WELCOME_TEXT, 'assistant');
        activeThinkRow = null;
        blockRows = {};
        turns.forEach((turn) => renderTurnHistory(turn.result));
        chat.scrollTop = chat.scrollHeight;
      }).catch(() => loadFlatHistory(id));
    } else {
      loadFlatHistory(null);
    }
  }

  function loadFlatHistory(conversationId) {
    const id = conversationId || localStorage.getItem(conversationKey);
    const url = id
      ? `/chat/history?conversation_id=${encodeURIComponent(id)}`
      : '/chat/history';
    fetch(url).then(response => {
      if (!response.ok) throw new Error('读取对话历史失败');
      return response.json();
    }).then(data => {
      if (data.conversation_id) {
        localStorage.setItem(conversationKey, data.conversation_id);
        document.dispatchEvent(new CustomEvent('conversation-changed'));
      }
      const messages = data.messages || [];
      if (!messages.length) {
        chat.textContent = '';
        add(WELCOME_TEXT, 'assistant');
        showNewChatOptions();
        return;
      }
      chat.textContent = '';
      add(WELCOME_TEXT, 'assistant');
      messages.forEach(item => {
        const clean = String(item.content || '').replace(/\[\[LABTHINK\]\]|\[\[LABCARD\]\]/g, '');
        add(clean, item.role === 'user' ? 'user' : 'assistant');
      });
      chat.scrollTop = chat.scrollHeight;
    }).catch(() => {});
  }

  window.switchConversation = function (id) {
    if (!id) return;
    stopCurrentResponse(false);
    localStorage.setItem(conversationKey, id);
    activeThinkRow = null; blockRows = {};
    turnStore.clear();
    window.runClearStream?.();
    clearChat();
    loadHistory(id);
    document.dispatchEvent(new CustomEvent('conversation-changed', { detail: { conversationId: id } }));
    input?.focus();
  };

    document.addEventListener('click', event => {
      const phone = event.target.closest('#sh-phone');
      if (!phone) return;
      window.open('/phone', '_blank');
    });


  document.addEventListener('click', event => {
    const button = event.target.closest('#sh-new-chat');
    if (!button) return;
    if (window.appNewConversation) {
      window.appNewConversation();
      return;
    }
    fetch('/chat/conversations', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
    }).then(r => r.json()).then(data => window.switchConversation?.(data.conversation_id));
  });

  loadHistory();


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
    window.__voiceTurnStartedAt = window.performance?.now?.() ?? Date.now();
    const modeSnapshot = window.consumeComposerModeSnapshot(form, 'text');
    stopCurrentResponse(false);
    const ownId = ++requestId;

    activeThinkRow = null; blockRows = {};
    add(message, 'user');
    input.value = '';
    const reply = add('正在思考…', 'assistant');
    activeReply = reply;
    const localRequestId = `web-${Date.now()}-${ownId}`;
    const localTurnId = `turn-${localRequestId}`;
    const assistantBlockId = modeSnapshot.interaction_mode === 'chat'
      ? `${localTurnId}:spoken` : `${localTurnId}:assistant`;
    turnStore.beginTurn({
      conversation_id: localStorage.getItem(conversationKey) || 'pending-conversation',
      request_id: localRequestId,
      turn_id: localTurnId,
      ...modeSnapshot,
      blocks: [{
        block_id: `${localTurnId}:user`,
        type: 'user_text',
        payload: { text: message },
      }],
    });
    if (modeSnapshot.interaction_mode === 'experiment') {
      window.publishProtocolContextBlocks?.(localTurnId).catch(() => {});
    }
    const publishAnswer = text => turnStore.upsertBlock({
      block_id: assistantBlockId,
      type: 'assistant_text',
      payload: modeSnapshot.interaction_mode === 'chat'
        ? { role: 'spoken', text } : { text },
    });
    activeController = new AbortController();
    stopButton.disabled = false;
    avatar('thinking');

    let answer = '';
    if (window.turnClient) {
      try {
        await window.turnClient.submitText(message, {
          modeSnapshot,
          requestId: localRequestId,
          turnId: localTurnId,
          signal: activeController.signal,
          onEvent: data => {
            if (data.type === 'turn_accepted') {
              if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
            } else if (data.type === 'turn_status') {
              publishAnswer(data.text || '正在处理…');
            } else if (data.type === 'turn_result') {
              const committed = data.turn;
              if (!committed) throw new Error('Turn 结果缺少 ConversationTurn');
              turnStore.acceptCommittedTurn(committed);
              const assistant = committed.blocks.find(block => block.type === 'assistant_text');
              answer = assistant?.payload?.text || '';
              settleCommittedReply(reply, assistant, publishAnswer);
              window.__voiceLastScreenAt = window.performance?.now?.() ?? Date.now();
              if (data.business?.kind === 'experiment') window.labStepsReload?.();
            } else if (data.type === 'voice_delivery') {
              window.consumeVoiceDelivery?.(data);
            } else if (data.type === 'turn_error') {
              throw new Error(data.detail || 'Turn 处理失败');
            } else if (data.type === 'done') {
              avatar('happy'); setTimeout(() => avatar('idle'), 1000);
              if (typeof loadExperiments === 'function') loadExperiments();
            }
          },
        });
      } catch (error) {
        if (error.name === 'AbortError' || ownId !== requestId) return;
        reply.textContent = `出错了：${error.message}`;
        avatar('interrupted'); setTimeout(() => avatar('idle'), 900);
      } finally {
        if (ownId === requestId) {
          activeController = null; activeReply = null;
          stopButton.disabled = true; input.focus();
        }
      }
      return;
    }
    try {
      if (modeSnapshot.interaction_mode === 'experiment') {
        await window.streamExperimentRecord(message, {
          ...modeSnapshot, request_id: localRequestId, turn_id: localTurnId
        }, data => {
          if (data.type === 'record_status') {
            publishAnswer(data.text || '正在保存原始事实…');
          } else if (data.type === 'record_error') {
            throw new Error(data.detail || '实验记录失败');
          } else if (data.type === 'record_result') {
            const result = data.data || {};
            window.publishRecordSurface?.(result);
            answer = (result.messages || []).map(item => item.text).filter(Boolean).join('\n');
            publishAnswer(answer || '原始事实已保存。');
            window.__voiceLastScreenAt = window.performance?.now?.() ?? Date.now();
            (result.voice_delivery_events || []).forEach(delivery => {
              window.consumeVoiceDelivery?.(delivery);
            });
          }
        });
        avatar('listening');
        return;
      }
      const response = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message, conversation_id: localStorage.getItem(conversationKey) || null,
          request_id: localRequestId, turn_id: localTurnId, ...modeSnapshot
        }),
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

          if (data.type === 'screen_delta' && data.text) {
            answer += data.text;
            publishAnswer(answer);
            window.__voiceLastScreenAt = window.performance?.now?.() ?? Date.now();
          } else if (data.type === 'voice_delivery') {
            window.consumeVoiceDelivery?.(data);
          } else if (data.type === 'delta' && data.text) {
            const text = data.text;
            if (text.indexOf('[[LABTHINK]]') >= 0) {
              const parts = text.split('[[LABTHINK]]');
              answer += parts[0];
              thinkBuffer += parts.slice(1).join('');
              turnStore.pushThink(thinkBuffer, true);
              publishAnswer(answer);
              continue;
            }
            if (text.indexOf('[[LABCARD]]') >= 0) {
              const parts = text.split('[[LABCARD]]');
              answer += parts[0];
              for (let i = 1; i < parts.length; i++) {
                try {
                  const view = JSON.parse(parts[i]);
                  turnStore.pushTool(view);
                } catch (e) { answer += parts[i]; }
              }
              publishAnswer(answer);
              continue;
            }
            answer += text;
            publishAnswer(answer);
          } else if (data.type === 'task_queued') {
            answer = data.answer; publishAnswer(answer);
            if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
            avatar('listening');
            window.refreshTaskPanel?.();
          } else if (data.type === 'done') {
            if (thinkBuffer) {
              turnStore.pushThink(thinkBuffer, false);
            } else {
              avatarThought('···');
            }
            if (data.conversation_id) localStorage.setItem(conversationKey, data.conversation_id);
            avatar('happy'); setTimeout(() => avatar('idle'), 1000);
            if (typeof loadExperiments === 'function') loadExperiments();
          } else if (data.type === 'error') {
            throw new Error(data.detail || '流式回复失败');
          }
        }
      }
      if (!answer) publishAnswer('模型没有返回文字内容。');
    } catch (error) {
      if (error.name === 'AbortError' || ownId !== requestId) return;
      reply.textContent = `出错了：${error.message}`;
      avatar('interrupted'); setTimeout(() => avatar('idle'), 900);
    } finally {
      if (ownId === requestId) { activeController = null; activeReply = null; stopButton.disabled = true; input.focus(); }
    }
  };
})();
