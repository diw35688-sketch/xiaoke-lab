(() => {
  const form = document.querySelector('#experiment-form');
  const title = form?.querySelector('h2');
  const save = document.querySelector('#save-experiment');
  const cancel = form?.querySelector('.modal-actions .btn:not(.primary)');
  if (!form || !save || !cancel) return;

  let pending = null;
  const preview = document.createElement('div');
  preview.style.cssText = 'display:none;margin:0 0 16px;padding:14px;border:1px solid #cbd7ff;border-radius:10px;background:#f5f7ff;line-height:1.8;font-size:14px';
  form.querySelector('.form-grid').before(preview);

  function leaveConfirmation() {
    pending = null;
    preview.style.display = 'none';
    form.querySelector('.form-grid').style.display = '';
    title.textContent = '新建实验';
    save.textContent = '下一步：确认信息';
    cancel.textContent = '取消';
  }

  window.closeModal = () => {
    document.querySelector('#modal').classList.remove('show');
    leaveConfirmation();
  };

  cancel.onclick = () => {
    if (pending) leaveConfirmation();
    else window.closeModal();
  };

  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!pending) {
      pending = Object.fromEntries(new FormData(form));
      if (!pending.name.trim()) return;
      const date = value => value ? new Date(value).toLocaleString('zh-CN') : '未设置';
      preview.innerHTML = `<b>请确认以下实验信息</b><br>实验：${escapeHtml(pending.name)}<br>开始：${date(pending.start_at)}<br>结束：${date(pending.end_at)}<br>仪器：${escapeHtml(pending.equipment || '未指定')}<br>目标：${escapeHtml(pending.goal || '未填写')}`;
      preview.style.display = 'block';
      form.querySelector('.form-grid').style.display = 'none';
      title.textContent = '确认创建实验';
      save.textContent = '确认创建';
      cancel.textContent = '返回修改';
      return;
    }

    save.disabled = true;
    try {
      const response = await fetch('/experiments', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(pending)});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail?.message || data.detail || '保存失败');
      notify('实验已创建');
      form.reset();
      window.closeModal();
      await loadExperiments();
      if (data.start_at) { viewDate = parseDate(data.start_at) || viewDate; renderCalendar(); }
    } catch (error) {
      notify(error.message);
    } finally {
      save.disabled = false;
    }
  };
})();
