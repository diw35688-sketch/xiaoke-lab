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
  let activeThinkRow = null, blockRows = {}, appliedToolUi = {};
  // 跨设备同步：网页版没有推送，手机看不到电脑上刚聊的新内容。
  // 记录已渲染的轮次数，轮询发现增加时只追加新轮次，不清屏不闪烁。
  let syncedTurnCount = -1, liveSyncTimer = null;
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

  function cleanDisplayText(text) {
    // 聊天里不显示 Markdown 裸符号：去掉 **、*、`、_ 等，只保留可读文字。
    return String(text || '')
      .replace(/[*_`]+/g, '')
      .replace(/^#{1,6}\s*/gm, '')
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  }

  function add(text, role) {
    const row = document.createElement('div'), bubble = document.createElement('div');
    row.className = `message ${role}`; bubble.className = 'bubble'; bubble.textContent = cleanDisplayText(text);
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
    var thinkAnchor = messageRow(reply);
    chat.insertBefore(row, (thinkAnchor && thinkAnchor.parentNode === chat) ? thinkAnchor : null);
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
    const artifact = view.artifact || {};
    const toolTitle = artifact.title || view.title || '工具调用';
    const toolLines = Array.isArray(artifact.lines) ? artifact.lines : (view.lines || []);
    const toolAction = Array.isArray(artifact.actions) && artifact.actions[0]
      ? artifact.actions[0] : view.ui_action;
    let row = blockRows[block.block_id];
    if (!row) {
      row = document.createElement('div');
      row.className = 'message tool';
      // 工具调用 = 仪器小票：默认折成一行「票根」，点票头展开全票。
      // 此前默认全展开，多次调用会把聊天流刷满（2026-08-30 纸面落地）。
      row.innerHTML = '<div class="chat-tool"><button type="button" class="chat-tool-head" aria-expanded="false"><span class="ic">⚙</span><span class="tt"></span><span class="st">进行中</span></button><div class="chat-tool-body"></div></div>';
      const toolCard = row.querySelector('.chat-tool');
      row.querySelector('.chat-tool-head').addEventListener('click', function () {
        const open = toolCard.classList.toggle('open');
        this.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      // 清单/准备/试剂/配方类卡片在右侧也展开显示。
      if (/清单|准备|试剂|配方|准备台/.test(toolTitle)) {
        toolCard.classList.add('open');
        row.querySelector('.chat-tool-head').setAttribute('aria-expanded', 'true');
      }
      var toolAnchor = messageRow(reply);
      chat.insertBefore(row, (toolAnchor && toolAnchor.parentNode === chat) ? toolAnchor : null);
      blockRows[block.block_id] = row;
    }
    const state = view.status === 'pending' ? '进行中' : (view.status === 'error' ? '失败' : '完成');
    const allLines = toolLines.filter(Boolean);
    const isChecklist = artifact.type === 'checklist' || artifact.type === 'prep_bench' || /清单|准备|试剂|配方|准备台/.test(toolTitle);
    const lines = isChecklist ? allLines : allLines.slice(0, 4);
    row.querySelector('.chat-tool-head .tt').textContent = cleanDisplayText(toolTitle);
    const st = row.querySelector('.chat-tool-head .st');
    st.textContent = state; st.className = 'st ' + (view.status || 'done');
    // 清单类 artifact 用统一渲染器画出可勾选结构，而不是一坨纯文本。
    const body = row.querySelector('.chat-tool-body');
    if (isChecklist && window.renderArtifact && artifact && (artifact.type === 'checklist' || artifact.type === 'prep_bench')) {
      body.innerHTML = window.renderArtifact(artifact);
    } else {
      body.textContent = cleanDisplayText(lines.join('\n'));
    }
    row.classList.toggle('tool-error', view.status === 'error');
    // 失败不允许被折叠藏住：出错时自动展开，用户必须看见原因。
    if (view.status === 'error') {
      row.querySelector('.chat-tool').classList.add('open');
      row.querySelector('.chat-tool-head').setAttribute('aria-expanded', 'true');
    }
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
      var cardAnchor = messageRow(reply);
      chat.insertBefore(row, (cardAnchor && cardAnchor.parentNode === chat) ? cardAnchor : null);
      blockRows[block.block_id] = row;
    }
    row.className = `message block-card tone-${view.tone}`;
    row.querySelector('.label').textContent = cleanDisplayText(view.label);
    row.querySelector('.title').textContent = cleanDisplayText(view.title);
    row.querySelector('.status').textContent = cleanDisplayText(view.status);
    row.querySelector('.chat-block-lines').textContent = cleanDisplayText(view.lines.join('\n'));
    row.querySelector('.chat-block-meta').textContent = cleanDisplayText(view.meta.join(' · '));
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
      } else if (block.type === 'tool_card') {
        if (activeReply) ensureToolRow(block, activeReply);
        else ensureCardRow(block, null);
        const artifact = block.payload?.artifact || {};
        const action = (Array.isArray(artifact.actions) && artifact.actions[0])
          || block.payload?.ui_action;
        if (action && !appliedToolUi[block.block_id]) {
          appliedToolUi[block.block_id] = true;
          if (window.appApplyUiAction) window.appApplyUiAction(action);
        }
      } else if (block.type === 'assistant_text' && activeReply) {
        if (block.payload.presentation === 'clarification_card') {
          const row = messageRow(activeReply);
          if (row) row.hidden = true;
          return;
        }
        activeReply.textContent = cleanDisplayText(block.payload.text || '');
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
      '.nco-ic{color:#64748b;margin-bottom:7px;display:flex}',
      '.nco-card:hover .nco-ic{color:#2563eb}',
      '.nco-title{font-weight:700;color:#0f172a;font-size:14px}',
      '.nco-desc{color:#64748b;font-size:12px;line-height:1.5;margin-top:3px}',
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
    if (window.logAction) window.logAction('new_chat_mode', { mode: mode });
    var input = document.getElementById('message');
    function showIntro(icon, title, description) {
      var opt = chat.querySelector('.new-chat-options');
      if (opt) opt.remove();
      var intro = chat.querySelector('.mode-intro');
      if (intro) intro.remove();
      var div = document.createElement('div');
      div.className = 'mode-intro';
      div.innerHTML = '<div class="mi-title">' + icon + ' ' + title + '</div>'
        + '<div class="mi-desc">' + description + '</div>';
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      if (input) input.focus();
    }
    if (mode === 'chat' || mode === 'free') {
      // 普通文字聊天和自由实验记录已移除；残留入口统一进入方案实验。
      if (window.shellShow) window.shellShow('protocols');
      return;
    }
    if (mode === 'protocol') {
      // 方案实验入口始终先打开方案页；是否沿用或更换当前方案由用户明确选择。
      if (window.shellShow) window.shellShow('protocols');
      return;
    }
    if (mode === 'template') {
      window.interactionModeState.select('template');
      showIntro(
        '✨',
        'AI制作方案/配方已开启',
        '通过对话创建或修改实验方案、试剂配方；可上传文本文件，PDF或图片请到方案页导入。'
      );
      return;
    }
    if (mode === 'storage') {
      window.interactionModeState.select('storage');
      // 制作储存库：跳转到储存库页面
      if (window.shellShow) window.shellShow('storage');
    }
  }

  function showNewChatOptions() {
    ensureNewChatStyles();
    if (chat.querySelector('.new-chat-options')) return;
    var MODE_ICONS = {
      protocol: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5h6"/><path d="M9 9h6"/><path d="M9 13h4"/><rect x="5" y="2" width="14" height="20" rx="2"/></svg>',
      template: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
      storage: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>'
    };
    var wrap = document.createElement('div');
    wrap.className = 'new-chat-options';
    wrap.innerHTML = [
      '<div class="nco-card" data-mode="protocol"><div class="nco-ic">' + MODE_ICONS.protocol + '</div><div class="nco-title">方案实验</div><div class="nco-desc">按当前方案逐步推进并记录</div></div>',
      '<div class="nco-card" data-mode="template"><div class="nco-ic">' + MODE_ICONS.template + '</div><div class="nco-title">AI制作方案/配方</div><div class="nco-desc">对话创建或修改；PDF/图片请到方案页导入</div></div>',
      '<div class="nco-card" data-mode="storage"><div class="nco-ic">' + MODE_ICONS.storage + '</div><div class="nco-title">制作储存库</div><div class="nco-desc">登记位置/物品/库存</div></div>'
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
        else if (reply.parentElement) reply.textContent = cleanDisplayText(payload.text || '');
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

  // ── 跨设备状态恢复 ─────────────────────────────────────────────
  // 手机 localStorage 和电脑独立；加载历史轮次后，把 lab_session_id 写回
  // localStorage，让手机继承电脑端的实验进度（"菌落PCR第1步、20管模板"等）。
  function restoreLabSessionsFromTurns(turns) {
    try {
      const SESSIONS_KEY = 'lab-agent-lab-sessions';
      let map = {};
      try { map = JSON.parse(localStorage.getItem(SESSIONS_KEY) || '{}'); } catch (_) {}
      turns.forEach(turn => {
        const item = turn.item || turn;
        const lsid = item.lab_session_id;
        if (!lsid) return;
        const ctx = item.interaction_mode || '';
        // 实验模式下的 lab_session 都按 protocol:<id> 或 free/template/storage 归类
        // 后端记录的 interaction_mode 只有 experiment/chat；实验上下文靠 blocks 推断
        // 但 lab_session_id 本身已经唯一标识一条实验轨道，直接写入即可。
        if (ctx === 'experiment') {
          // 尝试从 turn result 的 blocks 中提取 protocol_id
          let protocolId = '';
          const blocks = (item.result?.turn?.blocks || item.result?.blocks || []);
          for (const b of blocks) {
            if (b.type === 'system_status' && b.payload?.protocol_id) { protocolId = b.payload.protocol_id; break; }
          }
          const modeKey = protocolId ? ('protocol:' + protocolId) : 'protocol:';
          map[modeKey] = lsid;
        }
      });
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(map));
    } catch (_) { /* 静默失败，不影响历史渲染 */ }
  }

  function loadHistory(conversationId) {
    if (localStorage.getItem(freshChatKey)) {
      localStorage.removeItem(freshChatKey);
      return;
    }
    document.dispatchEvent(new CustomEvent('lab:context-preparing'));
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
        syncedTurnCount = turns.length;
        // 从历史轮次恢复 lab_session_id 到 localStorage，让手机端继承电脑端的实验状态
        restoreLabSessionsFromTurns(turns);
        startLiveSync();
        chat.scrollTop = chat.scrollHeight;
        document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { turns: turns.length } }));
      }).catch(() => loadFlatHistory(id));
    } else {
      // 本机没有 conversation_id（手机首次打开）：先从服务端拿最新会话 ID，
      // 再用 turn/history 加载结构化轮次（含 lab_session_id 等实验状态）。
      fetch('/chat/history').then(r => r.json()).then(d => {
        if (d.conversation_id) {
          localStorage.setItem(conversationKey, d.conversation_id);
          loadHistory(d.conversation_id);  // 递归走 turn/history 路径
        } else {
          loadFlatHistory(null);
        }
      }).catch(() => loadFlatHistory(null));
    }
  }

  function loadFlatHistory(conversationId) {
    document.dispatchEvent(new CustomEvent('lab:context-preparing'));
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
        // 首次加载/清除本地会话后，先固定一个后端会话 ID，
        // 避免第一条消息让每个 Turn 都生成新 UUID（一句话一个会话）。
        if (!localStorage.getItem(conversationKey)) {
          fetch('/chat/conversations', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
          }).then(r => r.json()).then(d => {
            if (d && d.conversation_id) {
              localStorage.setItem(conversationKey, d.conversation_id);
              document.dispatchEvent(new CustomEvent('conversation-changed'));
            }
            document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { fresh: true } }));
          }).catch(() => {
            document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { fresh: true } }));
          });
        } else {
          document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { fresh: true } }));
        }
        return;
      }
      chat.textContent = '';
      add(WELCOME_TEXT, 'assistant');
      messages.forEach(item => {
        const clean = String(item.content || '').replace(/\[\[LABTHINK\]\]|\[\[LABCARD\]\]/g, '');
        add(clean, item.role === 'user' ? 'user' : 'assistant');
      });
      // flat 历史没有 turn 计数；启动同步后，下次发现 turn 历史会自动全量切换。
      startLiveSync();
      chat.scrollTop = chat.scrollHeight;
      document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { messages: messages.length } }));
    }).catch(() => {
      document.dispatchEvent(new CustomEvent('lab:context-ready', { detail: { error: true } }));
    });
  }

  window.switchConversation = function (id) {
    if (!id) return;
    stopCurrentResponse(false);
    localStorage.setItem(conversationKey, id);
    activeThinkRow = null; blockRows = {};
    syncedTurnCount = -1;                                   // 换会话后重新计数
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

  // ── 跨设备增量同步 ──────────────────────────────────────────────
  // 网页版没有跨设备推送：电脑上发了新消息，手机不会自动知道；用户把手机切到
  // 后台再切回来时，聊天还停在旧画面。这里在「标签页重新可见」和「轻量定时轮询」
  // 时重新拉取历史，发现新轮次就增量追加。生成回复期间不刷新，避免打断正在打的字。
  async function syncNewTurns() {
    if (document.hidden) return;
    // 正在本机生成回复时不刷新——会吞掉正在流式输出的气泡。
    if (window.isAssistantBusy && window.isAssistantBusy()) return;
    const cid = localStorage.getItem(conversationKey);
    if (!cid) return;
    try {
      const res = await fetch('/turn/history?conversation_id=' + encodeURIComponent(cid));
      if (!res.ok) return;
      const data = await res.json();
      const turns = data.turns || [];
      if (turns.length <= syncedTurnCount) return;          // 没有新内容
      activeThinkRow = null;
      if (syncedTurnCount < 0) {
        // 首次从 flat 历史切换到 turn 历史：全量重渲染，避免重复。
        chat.textContent = '';
        add(WELCOME_TEXT, 'assistant');
        blockRows = {};
        turns.forEach(turn => renderTurnHistory(turn.result));
      } else {
        // 增量追加新增轮次，已有内容不动，不闪烁。
        const fresh = turns.slice(syncedTurnCount);
        fresh.forEach(turn => renderTurnHistory(turn.result));
      }
      syncedTurnCount = turns.length;
      chat.scrollTop = chat.scrollHeight;
    } catch (_) { /* 同步失败静默，下次轮询重试 */ }
  }

  function startLiveSync() {
    if (liveSyncTimer) return;
    liveSyncTimer = setInterval(syncNewTurns, 4000);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) syncNewTurns();                 // 手机切回前台立即同步
    });
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
    const assistantBlockId = `${localTurnId}:assistant`;
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
    if (modeSnapshot.experiment_context !== 'protocol') {
      window.publishProtocolContextBlocks?.(localTurnId).catch(() => {});
    }
    const publishAnswer = text => turnStore.upsertBlock({
      block_id: assistantBlockId,
      type: 'assistant_text',
      payload: { text },
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
              syncedTurnCount += 1;  // 标记本机刚完成的轮次，避免 syncNewTurns 重复渲染
              window.__voiceLastScreenAt = window.performance?.now?.() ?? Date.now();
              if (data.business?.kind === 'experiment') window.labStepsReload?.();
              if (typeof window.runReload === 'function') window.runReload();
              if (typeof window.chatHomeReload === 'function') window.chatHomeReload();
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
            syncedTurnCount += 1;  // 标记本机刚完成的轮次，避免重复渲染
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
            syncedTurnCount += 1;  // 标记本机刚完成的轮次，避免 syncNewTurns 重复渲染
            avatar('happy'); setTimeout(() => avatar('idle'), 1000);
            if (typeof loadExperiments === 'function') loadExperiments();
            if (typeof window.chatHomeReload === 'function') window.chatHomeReload();
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
