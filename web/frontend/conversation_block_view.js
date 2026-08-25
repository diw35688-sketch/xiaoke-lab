// Block → 统一聊天卡片视图模型。只做显示翻译，不改变业务事实。
(() => {
  const style = document.createElement('style');
  style.textContent = '.message.block-card{display:block}.chat-block{border:1px solid var(--bd-2);border-left:3px solid var(--brand);border-radius:10px;padding:10px 12px;background:var(--n-00);font-size:12px}.chat-block-head{display:flex;align-items:center;gap:7px}.chat-block-head .label{color:var(--n-500);font-size:11px}.chat-block-head .title{font-weight:600;color:var(--n-900);flex:1}.chat-block-head .status{color:var(--n-500);font-size:11px}.chat-block-lines{white-space:pre-wrap;color:var(--n-800);line-height:1.65;margin-top:6px}.chat-block-meta{color:var(--n-500);font-size:11px;margin-top:5px}.tone-danger .chat-block{border-left-color:var(--red-500);background:var(--red-50)}.tone-safe .chat-block{border-left-color:var(--green-500);background:var(--green-100)}.tone-record .chat-block{border-left-color:var(--amber-600)}.tone-confirm .chat-block{border-left-color:var(--brand);background:var(--brand-50)}';
  document.head.appendChild(style);
  const text = value => String(value == null ? '' : value);
  const compact = values => values.map(text).filter(Boolean);

  function conversationBlockView(block) {
    const payload = block && block.payload || {};
    switch (block && block.type) {
      case 'protocol_card':
        return {label: '实验方案', title: text(payload.title || '当前方案'), tone: 'info',
          status: text(payload.status), lines: compact([payload.summary]), meta: compact(payload.meta || [])};
      case 'step_card':
        return {label: `步骤 ${text(payload.number)}`, title: text(payload.title || '当前步骤'), tone: 'info',
          status: text(payload.status), lines: compact([payload.instruction].concat(payload.lines || [])), meta: compact(payload.meta || [])};
      case 'safety_alert':
        return {label: '安全提示', title: text(payload.title || payload.name || '请注意安全'),
          tone: payload.critical ? 'danger' : 'safe', status: payload.critical ? '重要' : '',
          lines: compact(payload.statements || payload.lines || []), meta: compact([payload.cas, payload.note])};
      case 'record_card': {
        const entities = Object.keys(payload.entities || {}).filter(key => payload.entities[key])
          .map(key => `${key} = ${payload.entities[key]}`);
        return {label: '实验记录', title: `第 ${text(payload.segment_id)} 段口述`, tone: 'record',
          status: text(payload.status || '已保存'), lines: compact([payload.transcript]), meta: entities};
      }
      case 'tool_card':
        return {label: 'Tool', title: text(payload.title || '工具调用'), tone: payload.status === 'error' ? 'danger' : 'tool',
          status: text(payload.status), lines: compact(payload.lines || []), meta: compact([payload.tool_call_id])};
      case 'confirmation_card':
        return {label: '待确认', title: text(payload.title || '请确认'), tone: 'confirm',
          status: text(payload.status), lines: compact(payload.lines || [payload.text]), meta: compact(payload.meta || [])};
      case 'system_status':
        return {label: '状态', title: text(payload.title || '系统状态'), tone: payload.error ? 'danger' : 'status',
          status: payload.running ? '进行中' : text(payload.status),
          lines: compact([payload.text].concat(payload.lines || [])), meta: compact(payload.meta || [])};
      default:
        return null;
    }
  }

  window.conversationBlockView = conversationBlockView;
})();
