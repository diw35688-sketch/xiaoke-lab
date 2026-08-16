(() => {
  const style = document.createElement('style');
  style.textContent = '.memory-mask{position:fixed;inset:0;z-index:11;display:none;background:rgba(17,25,42,.4)}.memory-mask.show{display:block}.memory-panel{position:absolute;right:0;top:0;width:min(480px,100%);height:100%;padding:25px;background:#fff;box-shadow:-15px 0 45px rgba(0,0,0,.16);overflow:auto}.memory-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.memory-head h2{margin:0}.memory-tools{margin-top:16px}.memory-item{padding:15px 0;border-bottom:1px solid #e6e9ef}.memory-category{display:inline-block;padding:3px 7px;border-radius:12px;background:#edf1ff;color:#465fc6;font-size:11px}.memory-content{margin:8px 0;color:#23304a;font-size:14px;line-height:1.6}.memory-time{color:#697586;font-size:11px}.memory-empty{padding:45px 0;text-align:center;color:#697586}.memory-delete{margin-top:8px;padding:5px 8px;border:1px solid #f0b9bf;border-radius:7px;background:white;color:#bd2837;cursor:pointer;font-size:12px}';
  document.head.appendChild(style);
  const nav = document.createElement('button');
  nav.className = 'nav-item'; nav.innerHTML = '<span>◈</span>长期记忆';
  const refresh = [...document.querySelectorAll('.nav-item')].find(item => item.textContent.includes('刷新数据'));
  refresh?.before(nav);
  const labels = {equipment: '设备', rule: '规则', preference: '偏好', general: '通用'};
  const mask = document.createElement('div');
  mask.className = 'memory-mask';
  mask.innerHTML = '<section class="memory-panel"><div class="memory-head"><div><h2>长期记忆</h2><p class="sub">仅显示你确认保存的信息</p></div><button class="btn" id="close-memories">关闭</button></div><div class="memory-tools"><button class="btn danger" id="clear-memories">清空长期记忆</button></div><div id="memory-list"></div></section>';
  document.body.appendChild(mask);
  const root = mask.querySelector('#memory-list');
  async function loadMemories() {
    root.innerHTML = '<p class="memory-empty">正在读取长期记忆…</p>';
    try {
      const response = await fetch('/memories'); if (!response.ok) throw Error('读取长期记忆失败');
      const items = await response.json();
      root.innerHTML = items.length ? items.map(item => `<article class="memory-item"><span class="memory-category">${labels[item.category] || '通用'}</span><div class="memory-content">${escapeHtml(item.content)}</div><div class="memory-time">保存于 ${new Date(item.created_at + 'Z').toLocaleString('zh-CN')}</div><button class="memory-delete" data-id="${item.id}">删除此记忆</button></article>`).join('') : '<p class="memory-empty">还没有已确认保存的长期记忆。</p>';
      root.querySelectorAll('.memory-delete').forEach(button => button.onclick = () => deleteOne(button.dataset.id));
    } catch (error) { root.innerHTML = `<p class="memory-empty">${error.message}</p>`; }
  }
  async function deleteOne(id) { if (!confirm('删除这条长期记忆？之后智能体将不再使用它。')) return; const r = await fetch(`/memories/${id}`, {method:'DELETE'}); if (!r.ok) return notify('删除失败'); notify('长期记忆已删除'); loadMemories(); }
  nav.onclick = () => { mask.classList.add('show'); loadMemories(); };
  mask.querySelector('#close-memories').onclick = () => mask.classList.remove('show');
  mask.onclick = event => { if (event.target === mask) mask.classList.remove('show'); };
  mask.querySelector('#clear-memories').onclick = async () => { if (!confirm('确定清空全部长期记忆？此操作不可恢复。')) return; const r = await fetch('/memories',{method:'DELETE'}); if (!r.ok) return notify('清空失败'); notify('长期记忆已清空'); loadMemories(); };
})();
