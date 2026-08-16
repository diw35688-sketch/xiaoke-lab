(() => {
  const style = document.createElement('style');
  style.textContent = '.history-mask{position:fixed;inset:0;z-index:10;display:none;background:rgba(17,25,42,.4)}.history-mask.show{display:block}.history-panel{position:absolute;right:0;top:0;width:min(480px,100%);height:100%;padding:25px;background:#fff;box-shadow:-15px 0 45px rgba(0,0,0,.16);overflow:auto}.history-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.history-head h2{margin:0}.history-tools{display:flex;gap:8px}.history-item{padding:15px 0;border-bottom:1px solid #e6e9ef}.history-item h3{margin:0;font-size:15px}.history-meta{margin:5px 0;color:#697586;font-size:12px;line-height:1.65}.danger{border:1px solid #f4c4c8;background:#fff;color:#bf2636}.delete-one{margin-top:7px;padding:5px 8px;border:1px solid #f0b9bf;border-radius:7px;background:white;color:#bd2837;cursor:pointer;font-size:12px}.history-empty{padding:45px 0;text-align:center;color:#697586}';
  document.head.appendChild(style);
  const nav = document.createElement('button');
  nav.className = 'nav-item'; nav.innerHTML = '<span>◷</span>历史清单';
  const refresh = [...document.querySelectorAll('.nav-item')].find(item => item.textContent.includes('刷新数据'));
  refresh?.before(nav);
  const mask = document.createElement('div');
  mask.className = 'history-mask';
  mask.innerHTML = '<section class="history-panel"><div class="history-head"><div><h2>历史清单</h2><p class="sub">已完成的所有实验</p></div><button class="btn" id="close-history">关闭</button></div><div class="history-tools"><button class="btn danger" id="clear-history">清空历史记录</button></div><div id="history-list"></div></section>';
  document.body.appendChild(mask);
  const root = mask.querySelector('#history-list');
  const format = value => value ? new Date(value).toLocaleString('zh-CN',{year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '未设置时间';
  async function loadHistory() {
    root.innerHTML = '<p class="history-empty">正在读取历史记录…</p>';
    try {
      const response = await fetch('/experiments/history'); if (!response.ok) throw Error('读取历史记录失败');
      const items = await response.json();
      root.innerHTML = items.length ? items.map(item => `<article class="history-item"><h3>${escapeHtml(item.name)}</h3><div class="history-meta">${format(item.start_at)}${item.equipment?' · '+escapeHtml(item.equipment):''}<br>${escapeHtml(item.goal || item.notes || '无备注')}</div><button class="delete-one" data-id="${item.id}">删除此记录</button></article>`).join('') : '<p class="history-empty">暂无已完成实验。</p>';
      root.querySelectorAll('.delete-one').forEach(button => button.onclick = () => deleteOne(button.dataset.id));
    } catch (error) { root.innerHTML = `<p class="history-empty">${error.message}</p>`; }
  }
  async function deleteOne(id) { if (!confirm('删除这条历史记录？此操作不可恢复。')) return; const r = await fetch(`/experiments/history/${id}`,{method:'DELETE'}); if (!r.ok) return notify('删除失败'); notify('历史记录已删除'); loadHistory(); }
  nav.onclick = () => { mask.classList.add('show'); loadHistory(); };
  mask.querySelector('#close-history').onclick = () => mask.classList.remove('show');
  mask.onclick = event => { if (event.target === mask) mask.classList.remove('show'); };
  mask.querySelector('#clear-history').onclick = async () => { if (!confirm('确定清空全部历史记录？此操作不可恢复。')) return; const r = await fetch('/experiments/history',{method:'DELETE'}); if (!r.ok) return notify('清空失败'); notify('历史记录已清空'); loadHistory(); };
})();
