(() => {
  const style = document.createElement('style');
  style.textContent = '.status{white-space:nowrap;padding:3px 7px;border-radius:20px;font-size:11px;font-weight:600}.status.pending{background:#fff4d8;color:#9a6400}.status.in_progress{background:#e3f7f1;color:#08745a}.status.completed{background:#ebeff5;color:#5c687a}.complete-btn{margin-top:9px;padding:5px 8px;border:1px solid #b7c5e7;border-radius:7px;background:#fff;color:#3158c8;font:inherit;font-size:12px;cursor:pointer}.complete-btn:hover{background:#eef3ff}';
  document.head.appendChild(style);
  const labels = {pending: '待开始', in_progress: '进行中', completed: '已完成'};
  const originalRenderList = window.renderList;

  window.renderList = function () {
    const root = document.querySelector('#experiment-list');
    if (!experiments.length) {
      root.innerHTML = '<p class="empty">还没有实验。点击“新建实验”开始安排吧。</p>';
      return;
    }
    root.innerHTML = experiments.map(item => `<article class="list-item"><div class="list-title"><span>${escapeHtml(item.name)}</span><span class="status ${item.status || 'pending'}">${labels[item.status] || '待开始'}</span></div><div class="meta">${item.start_at ? new Date(item.start_at).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '未安排时间'}${item.equipment ? ' · '+escapeHtml(item.equipment) : ''}${item.goal ? '<br>'+escapeHtml(item.goal) : ''}</div>${item.status !== 'completed' ? `<button class="complete-btn" data-id="${item.id}">✓ 标记为已完成</button>` : ''}</article>`).join('');
    root.querySelectorAll('.complete-btn').forEach(button => button.onclick = () => completeExperiment(button.dataset.id));
  };

  window.completeExperiment = async function (id) {
    if (!confirm('确认将此实验标记为“已完成”吗？')) return;
    try {
      const response = await fetch(`/experiments/${id}/status`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status: 'completed'})});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || '更新状态失败');
      notify('实验已标记为完成');
      await loadExperiments();
    } catch (error) {
      notify(error.message);
    }
  };

  if (originalRenderList && experiments?.length) window.renderList();
})();
