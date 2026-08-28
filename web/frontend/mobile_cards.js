// 移动端流程卡片：真实接口（默认）+ 演示数据（MOCK）双数据源
//
// 真实链路（正式产品形态）：
//   语音文本 → POST /chat → 大模型工具调用（record_observation / move_step / get_current_step）
//     → 后端确定性状态机（web/step_progress.py）判定 status
//     → 前端轮询 GET /protocols/session/steps → 只照着 status 渲染（✓/亮/暗）
//   手势/按钮翻页 → POST /protocols/session/move（next/prev，游标边界由状态机守护）
//   方案 B：步骤完成打勾后不自动翻页；翻页只靠用户明确指示（说"下一步"/上滑/按钮）。
// 前端永远不自己判定"步骤是否完成"。
(function () {
  'use strict';

  // ---------- 1. MOCK 数据（演示数据源用；与产品规格字段对齐） ----------
  var MOCK_CARDS = [
    {
      step: 1, total_steps: 5,
      title: '实验准备',
      instruction: '穿戴防护装备，核对试剂清单',
      description: '检查通风橱、洗眼器与废液桶位置。',
      warning: '本实验涉及浓盐酸，必须佩戴护目镜与手套。',
      status: 'completed', image: null,
      params: [{ k: '防护', v: '护目镜 + 手套' }, { k: '通风', v: '开启通风橱' }],
    },
    {
      step: 2, total_steps: 5,
      title: '设备初始化',
      instruction: '打开恒温水浴，设定 37 ℃',
      description: '等待示数稳定后再进行下一步。',
      warning: '先插电后开机；手湿时切勿触碰插座。',
      status: 'completed', image: null,
      params: [{ k: '温度', v: '37 ℃' }, { k: '等待', v: '示数稳定' }],
    },
    {
      step: 3, total_steps: 5,
      title: '加入试剂',
      instruction: '加入 20 mL A 溶液',
      description: '沿容器壁缓慢加入，避免产生气泡。',
      warning: '避免快速倾倒，防止液体飞溅。',
      status: 'waiting_user', image: null,
      params: [{ k: 'A 溶液', v: '20 mL' }],
    },
    {
      step: 4, total_steps: 5,
      title: '开始实验',
      instruction: '启动搅拌并开始计时',
      description: '搅拌转速 300 rpm，计时 30 分钟。',
      warning: '反应进行中不要打开容器盖。',
      status: 'waiting_user', image: null,
      params: [{ k: '转速', v: '300 rpm' }, { k: '计时', v: '30 分钟' }],
    },
    {
      step: 5, total_steps: 5,
      title: '查看结果',
      instruction: '记录颜色变化与仪器读数',
      description: '拍照留档，抄录示数到实验记录本。',
      warning: '读数异常时立即停止实验并报告负责人。',
      status: 'waiting_user', image: null,
      params: [{ k: '留档', v: '拍照' }, { k: '记录', v: '示数抄录' }],
    },
  ];

  // ---------- 2. 内部状态 ----------
  var currentIndex = 2;            // MOCK 起始：第 3 步"加入试剂"
  var transitioning = false;       // 动画期间锁，防止手势/按钮连点打乱节奏
  var cardOverflows = false;       // 卡片内容超一屏时为 true：滑动让给滚动
  var lastShownStatus = null;      // 上一次渲染的状态：完成动效只在"转变瞬间"触发
  var bubbleTimer = null;          // AI 回复气泡自动关闭计时器
  var voiceTimer = null;
  var dataSource = 'real';         // 'real'（真实接口）| 'mock'（演示数据）
  var realLastStep = null;         // 上次渲染的真实步骤号，用于判断翻页方向
  var realCard = null;             // 当前展示的真实卡片数据（completeCheck 用）
  var pollTimer = null;
  var renderStatuses = [];         // 分段状态（按步骤号 1..N 索引减 1）
  var renderCurIndex = 0;          // 当前步号（高亮分段用）

  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  // AI 形象（小科）：复用 PC 端立绘，状态由 setVoice 统一驱动
  var AVATAR = {
    idle:      { img: '/static/assets/assistant_portrait_transparent.png', label: '准备就绪' },
    listening: { img: '/static/assets/assistant_listening.png',           label: '正在聆听' },
    thinking:  { img: '/static/assets/assistant_thinking.png',            label: '正在思考' },
    speaking:  { img: '/static/assets/assistant_speaking.png',            label: '正在回答' },
    happy:     { img: '/static/assets/assistant_happy.png',               label: '已完成' },
  };

  function setVoice(kind, text) {
    var dot = el('vs-dot'), line = el('voice-status-text');
    if (dot && line) {
      if (voiceTimer) { clearTimeout(voiceTimer); voiceTimer = null; }
      dot.className = 'vs-dot' + (kind && kind !== 'idle' ? ' ' + kind : '');
      line.textContent = text;
    }
    // 同步 AI 形象：换立绘 + 状态文字 + 动画类
    var row = el('avatar-row'), img = el('avatar-img'), label = el('avatar-label');
    if (row && img && label) {
      var st = AVATAR[kind] || AVATAR.idle;
      if (img.getAttribute('src') !== st.img) img.src = st.img;
      label.textContent = st.label;
      row.className = 'm-avatar-row av-' + (AVATAR[kind] ? kind : 'idle');
    }
  }
  function setVoiceSoon(kind, text, ms) {
    setVoice(kind, text);
    voiceTimer = setTimeout(function () { setVoice('idle', '自动聆听中 · 直接说话即可'); }, ms);
  }

  var STATUS_TEXT = {
    waiting_user: '等你操作',
    running: '进行中',
    completed: '已完成',
    error: '需要处理',
  };

  // ---------- 3. 卡面主题（同前几轮，变量换肤 + localStorage） ----------
  var THEMES = [
    { id: 'mist', name: '晨雾蓝' },
    { id: 'night', name: '午夜深蓝' },
    { id: 'flat', name: '极简白' },
    { id: 'warm', name: '暖沙' },
    { id: 'kid', name: '怪盗扑克' },
  ];
  var currentTheme = 'mist';

  function themeName(id) {
    for (var i = 0; i < THEMES.length; i++) if (THEMES[i].id === id) return THEMES[i].name;
    return '晨雾蓝';
  }
  function applyTheme(id) {
    currentTheme = id || 'mist';
    var root = document.querySelector('.m-shell');
    if (root) {
      THEMES.forEach(function (t) { root.classList.remove('theme-' + t.id); });
      root.classList.add('theme-' + currentTheme);
    }
    Array.prototype.forEach.call(document.querySelectorAll('#theme-row .m-theme-btn'), function (b) {
      b.classList.toggle('on', b.dataset.theme === currentTheme);
    });
  }
  function renderThemeButtons() {
    var row = el('theme-row');
    if (!row) return;
    row.innerHTML = THEMES.map(function (t) {
      return '<button class="m-btn small m-theme-btn' + (t.id === currentTheme ? ' on' : '')
        + '" data-theme="' + t.id + '">' + t.name + '</button>';
    }).join('');
    Array.prototype.forEach.call(row.querySelectorAll('.m-theme-btn'), function (b) {
      b.onclick = function () { setTheme(b.dataset.theme); };
    });
  }
  function setTheme(id) {
    applyTheme(id);
    try { localStorage.setItem('mobileCardTheme', currentTheme); } catch (e) {}
    setVoiceSoon('idle', '卡面已切换：' + themeName(currentTheme), 1200);
  }

  // ---------- 4. 卡面背景图（同前几轮） ----------
  function loadBgImage(file) {
    if (!file) return;
    if (!/^image\//.test(file.type)) {
      setVoiceSoon('idle', '请选择图片文件（JPG/PNG/WebP）', 1500);
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        var scale = Math.min(1, 1200 / Math.max(img.width, img.height));
        var canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        var dataUrl = canvas.toDataURL('image/jpeg', 0.82);
        var root = document.querySelector('.m-shell');
        if (root) {
          root.style.setProperty('--card-bg-img', 'url("' + dataUrl + '")');
          root.classList.add('has-bgimg');
        }
        try { localStorage.setItem('mobileCardBg', dataUrl); } catch (e) {}
        setVoiceSoon('idle', '背景图已应用（已自动压缩）', 1500);
      };
      img.onerror = function () { setVoiceSoon('idle', '图片读取失败，换一张试试', 1500); };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  }
  function clearBgImage() {
    var root = document.querySelector('.m-shell');
    if (root) {
      root.classList.remove('has-bgimg');
      root.style.removeProperty('--card-bg-img');
    }
    try { localStorage.removeItem('mobileCardBg'); } catch (e) {}
    setVoiceSoon('idle', '背景图已清除', 1500);
  }
  function restoreBgImage() {
    var saved = null;
    try { saved = localStorage.getItem('mobileCardBg'); } catch (e) {}
    if (saved) {
      var root = document.querySelector('.m-shell');
      if (root) {
        root.style.setProperty('--card-bg-img', 'url("' + saved + '")');
        root.classList.add('has-bgimg');
      }
    }
  }
  function bindBgControls() {
    var choose = el('bg-choose'), clear = el('bg-clear'), fileInput = el('bg-file');
    if (!choose || !fileInput) return;
    choose.onclick = function () { fileInput.click(); };
    fileInput.onchange = function () {
      loadBgImage(fileInput.files[0]);
      fileInput.value = '';
    };
    if (clear) clear.onclick = clearBgImage;
  }

  // ---------- 5. 真实数据映射：/protocols/session/steps → Card 形状 ----------
  function cardFromProtocolView(view) {
    var s = view.step;
    var params = [];
    Object.keys(s.protocol_values || {}).forEach(function (k) {
      params.push({ k: k, v: String(s.protocol_values[k]) });
    });
    return {
      step: s.number,
      total_steps: view.protocol.total_steps,
      title: s.title,
      instruction: s.instruction,
      description: '',                       // 补充说明待后端提供；必测项走字段清单
      warning: s.hazard_note || '',
      status: s.status || 'waiting_user',
      type: s.card_type || 'action',
      must_record: (s.must_record || []).slice(),
      recorded: (s.recorded || []).slice(),
      missing: (s.missing || []).slice(),
      image: null,
      params: params,
    };
  }

  function freeModeCard() {
    return {
      step: 0, total_steps: 0,
      title: '自由记录模式',
      instruction: '尚未选择实验方案',
      description: '在下方 DEV 面板「实验方案」里选一份，即可开始卡片式流程。',
      warning: '',
      status: 'waiting_user',
      type: 'info',
      must_record: [],
      recorded: [],
      missing: [],
      image: null,
      params: [],
    };
  }

  // 实验完成结束卡：全部步骤已完成（后端 all_completed 判定），显示庆祝与记录汇总
  function endCard(view, recordCount) {
    var total = view.protocol.total_steps;
    return {
      step: total, total_steps: total,
      title: '实验完成',
      instruction: '全部 ' + total + ' 步已完成',
      description: recordCount != null
        ? ('本次实验共记录 ' + recordCount + ' 段口述')
        : '实验记录已保存，可在"本次记录"查看',
      warning: '',
      status: 'completed',
      type: 'result',
      must_record: [], recorded: [], missing: [],
      image: null,
      params: [],
      isEnd: true,
    };
  }

  // ---------- 6. 卡片渲染 ----------
  function cardHtml(card) {
    var params = (card.params || []).map(function (p) {
      return '<div class="m-param"><b>' + esc(p.k) + '</b><span>' + esc(p.v) + '</span></div>';
    }).join('');
    var warning = card.warning
      ? '<div class="m-card-warning">⚠ ' + esc(card.warning) + '</div>'
      : '';
    var image = card.image
      ? '<img class="m-card-image" src="' + esc(card.image) + '" alt="步骤图示">'
      : '';
    var segments = '';
    for (var n = 1; n <= card.total_steps; n++) {
      var st = renderStatuses[n - 1];
      // 分段状态：已完成=绿（打勾）· 当前=主题色 · 未到=灰
      var segCls = (st === 'completed') ? 'seg done'
        : (n === renderCurIndex) ? 'seg cur' : 'seg';
      segments += '<i class="' + segCls + '"></i>';
    }
    var check = card.status === 'completed' ? '<span class="m-check">✓</span>' : '';
    var endEmoji = card.isEnd ? '<div class="m-end-emoji">🎉</div>' : '';
    var ctype = card.type || (card.status === 'completed' ? 'result'
      : (card.status === 'error' ? 'error' : 'action'));
    // 必测字段清单：✓=已记录 ○=待记录（真实数据驱动）
    var checklist = '';
    if (card.must_record && card.must_record.length) {
      var recordedSet = {};
      (card.recorded || []).forEach(function (f) { recordedSet[f] = true; });
      checklist = '<div class="m-checklist">'
        + card.must_record.map(function (f) {
            // 已完成（含手动确认）的步骤，清单全勾，与 ✓ 徽标一致
            var ok = !!recordedSet[f] || card.status === 'completed';
            return '<span class="m-check-item' + (ok ? ' ok' : '') + '">'
              + (ok ? '✓' : '○') + ' ' + esc(f) + '</span>';
          }).join('')
        + '</div>';
    }
    // 结束卡不放"完成本步/下一步"按钮（任务已全部完成）
    var actions = card.isEnd ? '' : (
      '<div class="m-act-feedback" id="act-feedback" hidden></div>'
      + '<div class="m-card-actions">'
      +   '<button class="m-act primary" id="act-complete">完成本步 ✓</button>'
      +   '<button class="m-act" id="act-next">下一步 ›</button>'
      + '</div>'
    );
    return '<article class="m-card st-' + esc(card.status) + ' ty-' + ctype + '" data-step="' + card.step + '">'
      + '<div class="m-card-top">'
      + '<span class="m-step-chip">步骤 <b>' + card.step + '</b><i>/ ' + card.total_steps + '</i></span>'
      +   '<span class="m-status ' + esc(card.status) + '">' + (STATUS_TEXT[card.status] || esc(card.status)) + '</span>'
      + '</div>'
      + endEmoji
      + '<h1 class="m-card-title">' + esc(card.title) + check + '</h1>'
      + '<div class="m-card-instruction">' + esc(card.instruction) + '</div>'
      + (card.description ? '<div class="m-card-description">' + esc(card.description) + '</div>' : '')
      + (params ? '<div class="m-card-params">' + params + '</div>' : '')
      + checklist
      + image
      + warning
      + '<div class="m-card-steps">' + segments + '</div>'
      + actions
      + '</article>';
  }

  // 任务进度清单（横屏左栏）：同一份数据驱动的 ✓/→/○ 列表
  function renderProgressPanel(items) {
    var panel = el('progress-panel');
    if (!panel) return;
    if (!items || !items.length) { panel.innerHTML = ''; return; }
    panel.innerHTML = items.map(function (it) {
      var cls = it.status === 'completed' ? 'done' : (it.current ? 'cur' : '');
      var mark = it.status === 'completed' ? '✓' : (it.current ? '→' : '○');
      return '<div class="pp-item ' + cls + '"><span class="pp-mark">' + mark + '</span>'
        + '<span class="pp-title">' + esc(it.title) + '</span></div>';
    }).join('');
  }

  // applyState：统一状态入口（mock 与真实数据共用）
  function applyState(card, direction) {
    var stage = el('stage');
    if (!stage || !card) return;
    if (transitioning) return;

    var oldCard = stage.querySelector('.m-card');
    transitioning = true;

    function insert(enterClass) {
      stage.innerHTML = cardHtml(card);
      var node = stage.querySelector('.m-card');
      // 内容放不下时：允许卡片内滚动，并把滑动手势让位给滚动（翻页用按钮）
      if (node) {
        cardOverflows = node.scrollHeight > node.clientHeight + 2;
        stage.style.touchAction = cardOverflows ? 'auto' : 'none';
        // 完成仪式感：仅在"变为已完成"的那一次渲染触发（轮询刷新不重播）
        if (card.status === 'completed' && lastShownStatus !== 'completed') {
          node.classList.add('just-completed');
          if (navigator.vibrate) {
            try { navigator.vibrate([60, 40, 60]); } catch (e) {}
          }
        }
      }
      lastShownStatus = card.status;
      var completeBtn = node ? node.querySelector('#act-complete') : null;
      if (completeBtn) completeBtn.onclick = completeCheck;
      var nextBtn = node ? node.querySelector('#act-next') : null;
      if (nextBtn) nextBtn.onclick = function () { gestureNext(); };
      if (enterClass) {
        node.classList.add(enterClass);
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            node.classList.remove(enterClass);
            setTimeout(function () { transitioning = false; }, 190);
          });
        });
      } else {
        transitioning = false;
      }
    }

    if (!oldCard || !direction) {
      insert(null);
      return;
    }
    oldCard.classList.add(direction === 'next' ? 'out-up' : 'out-down');
    setTimeout(function () {
      insert(direction === 'next' ? 'in-from-down' : 'in-from-up');
    }, 170);
  }

  // ---------- 7. 真实接口 ----------
  function loadReal(direction) {
    return fetch('/protocols/session/steps')
      .then(function (r) { return r.json(); })
      .then(function (view) {
        var sel = el('protocol-select');
        if (view.mode !== 'protocol' || !view.step) {
          renderStatuses = [];
          renderCurIndex = 0;
          realCard = null;
          if (sel) sel.value = '';
          renderProgressPanel(null);
          applyState(freeModeCard(), null);
          return view;
        }
        renderStatuses = (view.all_steps || []).map(function (s) { return s.status || 'waiting_user'; });
        renderCurIndex = view.step.number;
        if (sel) sel.value = view.protocol ? view.protocol.id : '';
        renderProgressPanel((view.all_steps || []).map(function (s) {
          return { title: s.title, status: s.status || 'waiting_user', current: s.number === view.step.number };
        }));
        var newStep = view.step.number;
        var dir = direction || (realLastStep !== null && newStep !== realLastStep
          ? (newStep > realLastStep ? 'next' : 'prev') : null);
        realLastStep = newStep;
        // 全部步骤已完成且停在最后一步：展示"实验完成"结束卡
        if (view.all_completed && newStep === view.protocol.total_steps) {
          var end = endCard(view);
          realCard = end;
          applyState(end, dir);
          // 再取本次记录段数，回填到结束卡
          fetch('/record/history').then(function (r) { return r.json(); }).then(function (h) {
            if (dataSource !== 'real') return;
            var updated = endCard(view, (h && h.count) || 0);
            realCard = updated;
            applyState(updated, null);
          }).catch(function () {});
          return view;
        }
        var card = cardFromProtocolView(view);
        realCard = card;
        applyState(card, dir);
        return view;
      })
      .catch(function () {
        setVoiceSoon('idle', '连不上后端，已切换演示数据', 2000);
        setDataSource('mock');
      });
  }

  function moveReal(action) {
    if (transitioning) return;
    fetch('/protocols/session/move', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action }),
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
      if (!res.ok) {
        setVoiceSoon('idle', (res.d && res.d.detail) || '无法移动步骤', 1800);
        return;
      }
      loadReal(action === 'next' ? 'next' : 'prev');
    }).catch(function (e) {
      setVoiceSoon('idle', '网络错误：' + e.message, 1800);
    });
  }

  // 对话记忆：手机端不保存自己的会话，统一使用电脑端/服务端的最新会话。
  function convId() {
    return null;
  }
  function saveConvId(_id) {
    // 手机端不写本地会话，始终跟随电脑端最新会话。
  }
  // 与电脑端共用对话：每次直接从服务端取最新会话。
  function resolveConvId() {
    return fetch('/chat/conversations').then(function (r) { return r.json(); }).then(function (d) {
      var items = (d && d.items) || [];
      return (items[0] && items[0].conversation_id) || null;
    }).catch(function () { return null; });
  }
  function resetConversation() {
    setVoiceSoon('idle', '手机端不保存独立会话，重置无效；请到电脑端新建/切换会话', 1800);
  }

  // 语音文本 → /chat → 大模型工具调用（record_observation / move_step）→ 状态机判定
  // ---------- 小科回复气泡：AI 完整回复显示于此，8 秒后淡出，点按关闭 ----------
  function hideAiBubble() {
    var b = el('ai-bubble');
    if (!b) return;
    b.classList.remove('show');
    if (bubbleTimer) { clearTimeout(bubbleTimer); bubbleTimer = null; }
    setTimeout(function () { if (b) b.hidden = true; }, 250);
  }
  function showAiBubble(text) {
    var b = el('ai-bubble');
    if (!b || !text) return;
    b.innerHTML = '<span class="ab-name">小科</span><span class="ab-text"></span>';
    b.querySelector('.ab-text').textContent = text;
    b.hidden = false;
    requestAnimationFrame(function () { b.classList.add('show'); });
    if (bubbleTimer) clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(hideAiBubble, 8000);
  }

  function submitTranscript(text) {
    setVoice('thinking', 'AI 正在理解…');
    hideAiBubble();
    return resolveConvId().then(function (conversationId) {
      return fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, conversation_id: conversationId }),
      }).then(function (r) {
        return r.json().then(function (d) { return { ok: r.ok, d: d }; });
      });
    }).then(function (res) {
      if (!res.ok) {
        var err = (res.d && res.d.detail) || '未知错误';
        setVoice('idle', 'AI 处理失败');
        showAiBubble('⚠ ' + err);
        return;
      }
      if (res.d && res.d.conversation_id) saveConvId(res.d.conversation_id);
      var answer = (res.d && res.d.answer) || '';
      setVoice('speaking', 'AI：' + String(answer).slice(0, 40));
      showAiBubble(answer);          // 完整回复进气泡，不再截断
      appendChatLog('assistant', answer);
      loadReal();
    }).catch(function (e) {
      setVoice('idle', '网络错误');
      showAiBubble('⚠ 网络错误：' + e.message);
    });
  }

  // ---------- 8. 实验方案选择（真实数据源） ----------
  function bindProtocolSelect(sel) {
    if (!sel) return;
    fetch('/protocols').then(function (r) { return r.json(); }).then(function (d) {
      var items = d.protocols || [];
      sel.innerHTML = '<option value="">自由记录模式</option>'
        + items.map(function (p) {
            return '<option value="' + esc(p.id) + '">' + esc(p.title) + '（' + p.total_steps + ' 步）</option>';
          }).join('');
    }).catch(function () {});
    sel.onchange = function () {
      fetch('/protocols/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ protocol_id: sel.value || null }),
      }).then(function () {
        setVoiceSoon('idle', sel.value ? '方案已选择' : '已切到自由记录模式', 1500);
        loadReal();
      }).catch(function () {
        setVoiceSoon('idle', '选择方案失败', 1500);
      });
    };
  }

  function populateProtocols() {
    bindProtocolSelect(el('protocol-select'));
    bindProtocolSelect(el('m-protocol-select'));
  }

  function appendChatLog(role, text) {
    var log = el('m-chat-log');
    if (!log || !text) return;
    var div = document.createElement('div');
    div.className = 'm-msg ' + role;
    div.innerHTML = '<span class="m-msg-name">' + (role === 'user' ? '我' : '小科') + '</span><span class="m-msg-text"></span>';
    div.querySelector('.m-msg-text').textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  function submitTextChat(inputId) {
    var input = el(inputId || 'm-chat-input');
    var text = input ? input.value.trim() : '';
    if (!text) return;
    if (input) input.value = '';
    if (window.logAction) window.logAction('mobile_chat_send', { text: text.slice(0, 80) });
    appendChatLog('user', text);
    submitTranscript(text);
  }

  // ---------- 9. 数据源切换 ----------
  function setDataSource(source) {
    dataSource = source;
    var realBtn = el('ds-real'), mockBtn = el('ds-mock');
    if (realBtn) realBtn.classList.toggle('on', source === 'real');
    if (mockBtn) mockBtn.classList.toggle('on', source === 'mock');
    ['dev-complete', 'dev-deviation', 'dev-status'].forEach(function (id) {
      var b = el(id);
      if (b) b.disabled = (source !== 'mock');
    });
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (source === 'real') {
      realLastStep = null;
      loadReal();
      pollTimer = setInterval(function () { if (!transitioning) loadReal(); }, 3000);
    } else {
      renderMock(null);
      setVoiceSoon('idle', '已切换到演示数据（MOCK）', 1500);
    }
  }

  // ---------- 演示模式：隐藏 DEV 面板，只留右上角小齿轮 ----------
  var demoMode = false;
  function setDemoMode(on) {
    demoMode = on;
    try { localStorage.setItem('mobileDemoMode', on ? '1' : '0'); } catch (e) {}
    var dev = document.querySelector('.m-dev');
    var gear = el('gear-btn');
    var btn = el('dev-demo');
    if (dev) dev.style.display = on ? 'none' : '';
    if (gear) gear.hidden = !on;
    if (btn) btn.textContent = on ? '已进入演示模式' : '进入演示模式';
  }

  // ---------- 10. MOCK 演示动作（仅演示数据源可用） ----------
  function currentCard() { return MOCK_CARDS[currentIndex]; }

  function renderMock(direction) {
    renderStatuses = MOCK_CARDS.map(function (c) { return c.status; });
    renderCurIndex = currentIndex + 1;
    renderProgressPanel(MOCK_CARDS.map(function (c, i) {
      return { title: c.title, status: c.status, current: i === currentIndex };
    }));
    // 演示数据全部完成且停在最后一步：同样展示结束卡
    var allDone = MOCK_CARDS.every(function (c) { return c.status === 'completed'; });
    if (allDone && currentIndex === MOCK_CARDS.length - 1) {
      applyState({
        step: MOCK_CARDS.length, total_steps: MOCK_CARDS.length,
        title: '实验完成',
        instruction: '全部 ' + MOCK_CARDS.length + ' 步已完成',
        description: '演示数据 · 完成',
        warning: '',
        status: 'completed', type: 'result',
        must_record: [], recorded: [], missing: [], image: null, params: [],
        isEnd: true,
      }, direction);
      return;
    }
    applyState(currentCard(), direction);
  }

  function stepNext() {
    if (transitioning) return;
    if (currentIndex >= MOCK_CARDS.length - 1) {
      setVoiceSoon('speaking', '已经是最后一步（DEV 手势提示）', 1800);
      return;
    }
    currentIndex += 1;
    renderMock('next');
    setVoiceSoon('speaking', 'AI 正在播报：' + currentCard().title + '（模拟）', 2200);
  }

  function stepPrev() {
    if (transitioning) return;
    if (currentIndex <= 0) {
      setVoiceSoon('speaking', '已经是第一步（DEV 手势提示）', 1800);
      return;
    }
    currentIndex -= 1;
    renderMock('prev');
    setVoiceSoon('speaking', '已回到：' + currentCard().title + '（模拟）', 1800);
  }

  // 方案 B 语义（演示）：记录完成 → 打勾 ✓，不自动翻页
  function simulateRecordComplete() {
    if (transitioning) return;
    var card = currentCard();
    setVoice('thinking', '正在记录口述并判定…（模拟）');
    card.status = 'running';
    renderMock(null);
    setTimeout(function () {
      card.status = 'completed';
      renderMock(null);
      setVoiceSoon('happy', '本步已完成，已打勾 ✓（不自动翻页）', 2200);
    }, 900);
  }

  function simulateRecordDeviation() {
    if (transitioning) return;
    var card = currentCard();
    card.status = 'error';
    renderMock(null);
    setVoiceSoon('speaking', '记录到偏差，本步需要处理（模拟）', 2200);
  }

  function cycleStatus() {
    if (transitioning) return;
    var order = ['waiting_user', 'running', 'completed', 'error'];
    var card = currentCard();
    card.status = order[(order.indexOf(card.status) + 1) % order.length];
    renderMock(null);
    setVoiceSoon('idle', '状态样式切换为：' + STATUS_TEXT[card.status] + '（DEV 演示）', 1600);
  }

  // ---------- 11. 手势：真实模式=后端翻页；演示模式=本地翻页 ----------
  function gestureNext() {
    if (dataSource === 'real') moveReal('next');
    else stepNext();
  }
  function gesturePrev() {
    if (dataSource === 'real') moveReal('prev');
    else stepPrev();
  }

  // 卡片「完成本步」按钮：走显式完成接口，后端校验，不齐则拒绝。
  function completeCheck() {
    if (transitioning) return;
    if (dataSource === 'mock') { simulateRecordComplete(); return; }
    if (!realCard || !realCard.step) {
      setVoiceSoon('idle', '请先在 DEV 面板选择一份实验方案。', 2200);
      return;
    }
    // 用户手动确认完成：直接打勾（后端状态机接受并落盘），不再要求口述数据
    fetch('/protocols/session/steps/' + realCard.step + '/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manual: true }),
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        var msg;
        if (res.ok) {
          msg = '✓ 本步已完成（手动确认）。说"下一步"或点按钮翻页。';
          setVoiceSoon('happy', msg, 2600);
        } else {
          msg = (res.d && res.d.detail) || '本步还没完成。';
          setVoiceSoon('speaking', msg, 3000);
        }
        loadReal().then(function () { showCardFeedback(msg); });
      })
      .catch(function (e) {
        setVoiceSoon('idle', '请求失败：' + e.message, 2000);
      });
  }

  function showCardFeedback(text) {
    var fb = document.querySelector('#act-feedback');
    if (fb) { fb.textContent = text; fb.hidden = false; }
  }

  function bindGestures() {
    var stage = el('stage');
    if (!stage) return;
    var startY = null, startX = null;
    // 矮屏（横屏）模式：滑动让给卡片内部滚动，翻页用 ‹ › 按钮。
    var compactQuery = window.matchMedia ? window.matchMedia('(max-height: 520px)') : null;

    stage.addEventListener('touchstart', function (e) {
      startY = e.touches[0].clientY;
      startX = e.touches[0].clientX;
    }, { passive: true });

    stage.addEventListener('touchend', function (e) {
      if (startY === null) return;
      if (compactQuery && compactQuery.matches) return;   // 横屏：不抢滚动
      if (cardOverflows) return;                          // 卡片内容超屏：不抢滚动
      var dy = e.changedTouches[0].clientY - startY;
      var dx = e.changedTouches[0].clientX - startX;
      startY = null;
      if (Math.abs(dy) < 50) return;
      if (Math.abs(dx) > Math.abs(dy)) return;
      if (dy < 0) gestureNext();
      else gesturePrev();
    }, { passive: true });
  }

  // ---------- 12. 绑定 ----------
  function showChatView() {
    var chat = el('chat-view'), card = el('card-view');
    if (chat) chat.style.display = 'block';
    if (card) card.style.display = 'none';
  }
  function showCardView() {
    var chat = el('chat-view'), card = el('card-view');
    if (chat) chat.style.display = 'none';
    if (card) card.style.display = 'block';
    loadReal();
  }

  function bind() {
    var prev = el('btn-prev'), next = el('btn-next');
    if (prev) prev.onclick = gesturePrev;
    if (next) next.onclick = gestureNext;

    var complete = el('dev-complete'), deviation = el('dev-deviation'), statusBtn = el('dev-status');
    if (complete) complete.onclick = simulateRecordComplete;
    if (deviation) deviation.onclick = simulateRecordDeviation;
    if (statusBtn) statusBtn.onclick = cycleStatus;

    var dsReal = el('ds-real'), dsMock = el('ds-mock');
    if (dsReal) dsReal.onclick = function () { setDataSource('real'); };
    if (dsMock) dsMock.onclick = function () { setDataSource('mock'); };

    var resetConv = el('dev-reset-conv');
    if (resetConv) resetConv.onclick = resetConversation;

    document.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight') gestureNext();
      if (e.key === 'ArrowLeft') gesturePrev();
    });
    bindGestures();

    var bubble = el('ai-bubble');
    if (bubble) bubble.onclick = hideAiBubble;

    var gearBtn = el('gear-btn');
    if (gearBtn) gearBtn.onclick = function () { setDemoMode(false); };
    var demoBtn = el('dev-demo');
    if (demoBtn) demoBtn.onclick = function () { setDemoMode(true); };
    var savedDemo = '0';
    try { savedDemo = localStorage.getItem('mobileDemoMode') || '0'; } catch (e) {}
    setDemoMode(savedDemo === '1');

    var savedTheme = 'mist';
    try { savedTheme = localStorage.getItem('mobileCardTheme') || 'mist'; } catch (e) {}
    applyTheme(savedTheme);
    renderThemeButtons();
    restoreBgImage();
    bindBgControls();
    var chatInput = el('m-chat-input'), chatSend = el('m-chat-send');
    if (chatInput && chatSend) {
      chatSend.onclick = function () { submitTextChat('m-chat-input'); };
      chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); submitTextChat('m-chat-input'); }
      });
    }
    var cardInput = el('m-chat-card-input'), cardSend = el('m-chat-card-send');
    if (cardInput && cardSend) {
      cardSend.onclick = function () { submitTextChat('m-chat-card-input'); };
      cardInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); submitTextChat('m-chat-card-input'); }
      });
    }
    var startBtn = el('m-start-experiment');
    if (startBtn) startBtn.onclick = showCardView;
    var backBtn = el('m-back-chat');
    if (backBtn) backBtn.onclick = showChatView;
    populateProtocols();
    showChatView();   // 默认进入聊天，用户点“开始实验”后才进流程卡片
    // 预加载 AI 形象立绘，切状态不闪
    Object.keys(AVATAR).forEach(function (k) {
      var preload = new Image();
      preload.src = AVATAR[k].img;
    });
    setDataSource('real');   // 默认走真实接口
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }

  // ---------- 13. 对外接口 ----------
  window.MobileCards = {
    applyState: applyState,
    currentCard: currentCard,
    setVoice: setVoice,
    setTheme: setTheme,
    submitTranscript: submitTranscript,
    submitTextChat: submitTextChat,
    resetConversation: resetConversation,
    isReal: function () { return dataSource === 'real'; },
    MOCK_CARDS: MOCK_CARDS,
  };
})();
