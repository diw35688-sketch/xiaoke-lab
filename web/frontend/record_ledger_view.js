// Render the unified experiment ledger without changing business state.
(() => {
  const style = document.createElement('style');
  style.textContent = '.record-ledger{max-width:900px}.ledger-summary{color:#64748b;font-size:12px;margin-bottom:14px}.ledger-section{margin-bottom:20px}.ledger-section h3{font-size:14px;color:#0f172a;margin:0 0 9px}.ledger-steps{display:flex;gap:8px;flex-wrap:wrap}.ledger-step{display:flex;gap:8px;align-items:center;border:1px solid #e2e8f0;border-radius:9px;padding:8px 11px;background:#fff;font-size:12px}.ledger-step span{color:#64748b}.ledger-completed{border-left:3px solid #16a34a}.ledger-left_with_pending{border-left:3px solid #d97706}.ledger-in_progress{border-left:3px solid #2563eb}.ledger-question,.ledger-record{background:#fff;border:1px solid #e2e8f0;border-radius:11px;padding:12px 14px;margin-bottom:9px}.ledger-question{position:relative;border-left:3px solid #2563eb}.ledger-question>span{position:absolute;right:14px;top:12px;color:#64748b;font-size:11px}.ledger-question p,.ledger-record p{margin:7px 0;color:#334155;line-height:1.6}.ledger-question small{color:#b45309}.ledger-answers{margin-top:10px;border-top:1px dashed #cbd5e1;padding-top:8px}.ledger-answer{background:#f8fafc;border-radius:7px;padding:8px 10px;margin-top:6px;font-size:12px}.ledger-answer div{margin-top:4px;color:#475569}.ledger-answer-label{color:#64748b;margin-right:6px}.ledger-written{display:inline-block;background:#dcfce7;color:#166534;border-radius:5px;padding:2px 7px;margin:2px 4px 0 0}.ledger-unlinked{color:#94a3b8}.ledger-record-head{display:flex;gap:10px;color:#94a3b8;font-size:11px}.ledger-record-head b{color:#334155}.ledger-entity{display:inline-block;background:#e0e7ff;color:#3730a3;border-radius:5px;padding:2px 7px;margin:2px 4px 2px 0;font-size:11px}.ledger-deviation{background:#fff7ed;color:#c2410c;border-radius:7px;padding:7px 9px;margin-top:7px;font-size:12px}.ledger-empty{color:#94a3b8;font-size:13px}';
  document.head.appendChild(style);
  const esc = value => String(value == null ? '' : value).replace(
    /[&<>]/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[char])
  );
  const statusLabel = {
    not_started: '未开始',
    in_progress: '进行中',
    left_with_pending: '有暂缓问题',
    completed: '已完成',
    active: '待回答',
    deferred: '已暂缓',
    resolved: '已解决',
    expired: '已失效',
  };
  const fieldLabel = {
    action: '操作', object: '对象', instrument: '仪器',
    amount_value: '体积或质量数值', amount_unit: '体积或质量单位',
    concentration: '浓度', temperature: '温度', duration: '时间',
    condition: '实验条件', observation: '观察现象',
  };

  function renderProtocol(protocol) {
    if (!protocol) return '';
    const statuses = protocol.step_statuses || {};
    const numbers = Object.keys(statuses).sort((a, b) => Number(a) - Number(b));
    if (!numbers.length) return '';
    return '<section class="ledger-section"><h3>方案步骤</h3><div class="ledger-steps">'
      + numbers.map(number => {
        const status = statuses[number];
        const current = Number(number) === Number(protocol.current_step_number);
        return '<div class="ledger-step ledger-' + esc(status) + '">'
          + '<b>步骤 ' + esc(number) + (current ? '（当前）' : '') + '</b>'
          + '<span>' + esc(statusLabel[status] || status) + '</span></div>';
      }).join('') + '</div></section>';
  }

  function renderClarifications(items) {
    if (!items || !items.length) return '';
    return '<section class="ledger-section"><h3>待确认账</h3>'
      + items.map(item => '<div class="ledger-question">'
        + '<div><b>问题 ' + esc(item.display_number) + '</b>'
        + (item.protocol_step_number ? ' · 步骤 ' + esc(item.protocol_step_number) : '')
        + '</div><span>' + esc(statusLabel[item.status] || item.status) + '</span>'
        + '<p>' + esc(item.question) + '</p>'
        + (item.missing_fields?.length
          ? '<small>仍缺：' + item.missing_fields.map(esc).join('、') + '</small>'
          : '')
        + renderAnswers(item.answers) + '</div>').join('') + '</section>';
  }

  function renderAnswers(answers) {
    if (!answers || !answers.length) return '';
    return '<div class="ledger-answers"><b>补充答案</b>' + answers.map(answer => {
      const fields = answer.written_fields || [];
      const written = fields.length
        ? fields.map(item => '<span class="ledger-written">'
          + esc(fieldLabel[item.field] || item.field)
          + '=' + esc(item.value) + '</span>').join('')
        : '<span class="ledger-unlinked">未找到可验证的字段写入关联</span>';
      return '<div class="ledger-answer"><div><span class="ledger-answer-label">用户答了</span>'
        + esc(answer.raw_text) + '</div><div><span class="ledger-answer-label">最终写入</span>'
        + written + '</div></div>';
    }).join('') + '</div>';
  }

  // 时间戳统一按浏览器本地时区显示（数据库存的是 UTC，不能直接取原字符串的 HH:MM）。
  function parseLocal(value) {
    if (!value) return null;
    let text = String(value).trim();
    // 兼容“2026-09-03 06:32:45”这类无时区的 SQLite 时间：按 UTC 解析。
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
      text = text.replace(' ', 'T') + 'Z';
    }
    const date = new Date(text);
    return isNaN(date.getTime()) ? null : date;
  }

  function pad2(value) {
    return String(value).padStart(2, '0');
  }

  function localDateTime(value) {
    const date = parseLocal(value);
    if (!date) return '';
    return date.getFullYear() + '-' + pad2(date.getMonth() + 1) + '-'
      + pad2(date.getDate()) + ' ' + pad2(date.getHours()) + ':'
      + pad2(date.getMinutes());
  }

  function clockOf(value) {
    const date = parseLocal(value);
    return date ? pad2(date.getHours()) + ':' + pad2(date.getMinutes()) : '';
  }

  function renderRecords(items) {
    if (!items || !items.length) {
      return '<section class="ledger-section"><h3>实验口述</h3>'
        + '<div class="ledger-empty">当前实验还没有结构化口述记录。</div></section>';
    }
    // 记录本条目：时间戳挂红线外侧、红线上一个点、顶部胶带、右上「已记录」印章。
    // 装饰件（胶带/印章/页边时间戳）只在纸面皮肤下显形，经典外观仍是干净卡片。
    return '<section class="ledger-section nb-log"><h3>实验口述</h3>'
      + items.map(item => {
        const entities = Object.keys(item.entities || {}).filter(key => item.entities[key])
          .map(key => '<span class="ledger-entity fact">' + esc(key) + ' = '
            + esc(item.entities[key]) + '</span>').join('');
        const evaluation = item.evaluation || {};
        const step = item.step?.step?.number;
        const clock = clockOf(item.at);
        const deviations = (evaluation.deviations || []).map(value =>
          '<div class="ledger-deviation nb-dev"><b>偏差：'
            + esc(fieldLabel[value.field] || value.field) + '</b>'
            + '<div>期望：' + esc(value.protocol_value)
            + ' · 实际：' + esc(value.actual_value) + '</div></div>'
        ).join('');
        return '<article class="ledger-record nb-entry">'
          + (clock ? '<span class="nb-ts">' + esc(clock) + '</span>' : '')
          + '<span class="nb-dot" aria-hidden="true"></span>'
          + '<span class="nb-tape" aria-hidden="true"></span>'
          + '<div class="ledger-record-head nb-head">'
          + '<b>第 ' + esc(item.segment_id) + ' 段</b>'
          + (step ? '<span class="nb-step">方案步骤 ' + esc(step) + '</span>' : '')
          + '<span class="nb-at">' + esc(localDateTime(item.at)) + '</span></div>'
          + '<p class="nb-text">' + esc(item.transcript) + '</p>'
          + (entities ? '<div class="nb-facts">' + entities + '</div>' : '')
          + deviations
          + '<span class="nb-stamp" aria-hidden="true">已记录</span>'
          + '</article>';
      }).join('') + '</section>';
  }

  function renderExperimentLedger(data) {
    const header = '<div class="ledger-summary">实验会话 ' + esc(data.session_id)
      + ' · ' + esc(data.count || 0) + ' 段口述 · 状态版本 '
      + esc(data.revision == null ? '—' : data.revision) + '</div>';
    return '<div class="record-ledger">' + header
      + renderProtocol(data.protocol)
      + renderClarifications(data.clarifications)
      + renderRecords(data.items) + '</div>';
  }

  window.renderExperimentLedger = renderExperimentLedger;
  window.renderLedgerRecords = renderRecords;
  window.renderLedgerProtocol = renderProtocol;
  window.renderLedgerClarifications = renderClarifications;
})();
