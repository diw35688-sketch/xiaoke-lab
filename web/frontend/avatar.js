(() => {
  const labels = { idle: '准备就绪', listening: '正在聆听', thinking: '正在思考', speaking: '正在回答', happy: '已完成', interrupted: '已暂停' };
  const portraits = {
    idle: '/static/assets/assistant_portrait_transparent.png',
    listening: '/static/assets/assistant_listening.png',
    thinking: '/static/assets/assistant_thinking.png',
    speaking: '/static/assets/assistant_speaking.png',
    happy: '/static/assets/assistant_happy.png',
    interrupted: '/static/assets/assistant_portrait_transparent.png',
    mouth_open: '/static/assets/assistant_mouth_open.png'
  };
  const eyeFrames = {
    look_upper_left: '/static/assets/eye_frames/look_upper_left.png',
    look_up: '/static/assets/eye_frames/look_up.png',
    look_upper_right: '/static/assets/eye_frames/look_upper_right.png',
    look_left: '/static/assets/eye_frames/look_left.png',
    look_center: '/static/assets/eye_frames/look_center.png',
    look_right: '/static/assets/eye_frames/look_right.png',
    look_lower_left: '/static/assets/eye_frames/look_lower_left.png',
    look_down: '/static/assets/eye_frames/look_down.png',
    look_lower_right: '/static/assets/eye_frames/look_lower_right.png'
  };
  const positionKey = 'lab-agent-avatar-position'; let settleTimer = null; let speakTimer = null; let speakFrame = false;

  function clampPosition(widget, left, top) { const width = widget.offsetWidth || 225, height = widget.offsetHeight || 310; return { left: Math.max(4, Math.min(left, window.innerWidth - width - 4)), top: Math.max(4, Math.min(top, window.innerHeight - height - 4)) }; }
  function place(widget, left, top, save = false) { const pos = clampPosition(widget, left, top); widget.style.left = `${pos.left}px`; widget.style.top = `${pos.top}px`; widget.style.right = 'auto'; widget.style.bottom = 'auto'; if (save) localStorage.setItem(positionKey, JSON.stringify(pos)); }
  function restorePosition(widget) { try { const saved = JSON.parse(localStorage.getItem(positionKey)); if (Number.isFinite(saved?.left) && Number.isFinite(saved?.top)) place(widget, saved.left, saved.top); } catch (_) { localStorage.removeItem(positionKey); } }
  function enableDragging(widget) {
    let pointerId = null, startX = 0, startY = 0, originLeft = 0, originTop = 0, moved = false;
    widget.addEventListener('pointerdown', event => { if (event.button !== 0 && event.pointerType !== 'touch') return; const rect = widget.getBoundingClientRect(); pointerId = event.pointerId; startX = event.clientX; startY = event.clientY; originLeft = rect.left; originTop = rect.top; widget.classList.add('is-dragging'); widget.setPointerCapture?.(pointerId); event.preventDefault(); });
    widget.addEventListener('pointermove', event => { if (event.pointerId === pointerId) { const dx = event.clientX - startX, dy = event.clientY - startY; if (Math.abs(dx) + Math.abs(dy) > 4) { moved = true; widget.dataset.moved = '1'; } place(widget, originLeft + dx, originTop + dy); } });
    const finish = event => { if (event.pointerId !== pointerId) return; const rect = widget.getBoundingClientRect(); place(widget, rect.left, rect.top, true); widget.classList.remove('is-dragging'); pointerId = null; widget.dataset.moved = moved ? '1' : ''; moved = false; };
    widget.addEventListener('pointerup', finish); widget.addEventListener('pointercancel', finish);
    window.addEventListener('resize', () => { const rect = widget.getBoundingClientRect(); place(widget, rect.left, rect.top, true); });
  }
  function create() {
    if (document.querySelector('#assistant-avatar')) return;
    const style = document.createElement('style'); style.textContent = `
      #assistant-avatar{position:fixed;right:18px;bottom:72px;z-index:25;width:225px;background:transparent;user-select:none;touch-action:none;cursor:grab;filter:drop-shadow(0 12px 14px rgba(32,58,107,.22));transition:filter .2s ease}
      #assistant-avatar.is-dragging{cursor:grabbing;filter:drop-shadow(0 17px 20px rgba(32,58,107,.3))}#assistant-avatar .portrait{position:relative;width:100%;height:278px;overflow:visible;pointer-events:none;transition:transform .12s ease-out;will-change:transform}
      #assistant-avatar .portrait img{display:block;width:100%;height:100%;object-fit:contain;object-position:center bottom;transform-origin:50% 88%;animation:avatarBreathe 3.2s ease-in-out infinite;transition:opacity .12s ease}
      #assistant-avatar .avatar-info{display:flex;align-items:center;justify-content:center;gap:7px;width:max-content;min-height:29px;margin:-4px auto 0;padding:5px 11px;border:1px solid rgba(88,128,204,.3);border-radius:999px;background:rgba(255,253,248,.88);box-shadow:0 4px 15px rgba(37,66,122,.14);color:#25477e;font-size:12px;backdrop-filter:blur(6px);pointer-events:none}
      #assistant-avatar .avatar-name{font-weight:800;color:#193d78}#assistant-avatar .avatar-dot{display:inline-block;width:7px;height:7px;margin-right:4px;border-radius:50%;background:#83a3d8}#assistant-avatar .avatar-thought{position:absolute;z-index:1;top:10px;right:0;display:none;min-width:34px;max-width:210px;padding:7px 10px;border-radius:14px;background:rgba(255,255,255,.96);border:1px solid rgba(88,128,204,.16);color:#5473ac;font-weight:600;letter-spacing:0;line-height:1.55;white-space:pre-wrap;word-break:break-word;text-align:left;box-shadow:0 6px 18px rgba(42,71,126,.18);pointer-events:none}
      #assistant-avatar.is-listening .avatar-dot{background:#40a576;box-shadow:0 0 0 5px rgba(64,165,118,.15);animation:avatarPulse 1s infinite}#assistant-avatar.is-thinking .avatar-dot{background:#e0a241;animation:avatarBlink .75s infinite}#assistant-avatar.is-thinking .avatar-thought{display:block;animation:avatarThought 1s ease-in-out infinite}#assistant-avatar.is-speaking img{animation:avatarTalk .34s ease-in-out infinite alternate}#assistant-avatar.is-speaking .avatar-dot{background:#4d83e9;animation:avatarPulse .7s infinite}#assistant-avatar.is-happy .avatar-dot{background:#e3816c}#assistant-avatar.is-interrupted img{filter:grayscale(.22) saturate(.78)}#assistant-avatar.is-interrupted .avatar-dot{background:#a98563}
      @keyframes avatarBreathe{50%{transform:translateY(-3px) scale(1.012)}}@keyframes avatarTalk{to{transform:translateY(-4px) scale(1.03)}}@keyframes avatarPulse{50%{transform:scale(1.35);box-shadow:0 0 0 8px rgba(64,130,226,.07)}}@keyframes avatarBlink{50%{opacity:.2}}@keyframes avatarThought{50%{transform:translateY(-3px);opacity:.65}}@media(max-width:720px){#assistant-avatar{right:4px;bottom:61px;width:150px}#assistant-avatar .portrait{height:187px}#assistant-avatar .avatar-info{min-height:25px;padding:4px 8px;font-size:10px}}
    `; document.head.appendChild(style);
    const widget = document.createElement('aside'); widget.id = 'assistant-avatar'; widget.className = 'is-idle'; widget.setAttribute('aria-label', '可拖动的实验助手虚拟形象');
    widget.innerHTML = '<div class="portrait"><img src="/static/assets/assistant_portrait_transparent.png" alt="小科实验助手"><span class="avatar-thought">···</span></div><div class="avatar-info"><span class="avatar-name">小科</span><span><i class="avatar-dot"></i><span class="avatar-label">准备就绪</span></span></div>';
    document.body.appendChild(widget); Object.values(portraits).forEach(src => { const image = new Image(); image.src = src; }); restorePosition(widget); enableDragging(widget);
      widget.addEventListener('click', () => { if (widget.dataset.moved !== '1' && window.phoneCallToggle) window.phoneCallToggle(); });
  }
  function clearSpeakTimer() {
    if (speakTimer) { clearInterval(speakTimer); speakTimer = null; speakFrame = false; }
  }
  function startSpeakFrames(widget) {
    clearSpeakTimer();
    const image = widget.querySelector('.portrait img');
    speakFrame = false;
    image.src = portraits.mouth_open;
    speakTimer = setInterval(function () {
      speakFrame = !speakFrame;
      image.src = speakFrame ? portraits.idle : portraits.mouth_open;
    }, 160);
  }
  function setState(nextState) {
    if (!labels[nextState]) nextState = 'idle'; const widget = document.querySelector('#assistant-avatar'); if (!widget) return;
    const dragging = widget.classList.contains('is-dragging'); widget.className = `is-${nextState}${dragging ? ' is-dragging' : ''}`; widget.querySelector('.avatar-label').textContent = labels[nextState];
    clearTimeout(settleTimer);
    widget.dataset.state = nextState;
    if (nextState === 'speaking') { startSpeakFrames(widget); }
    else { clearSpeakTimer(); const image = widget.querySelector('.portrait img'); if (image.getAttribute('src') !== portraits[nextState]) image.src = portraits[nextState]; }
  }
  window.setAvatarState = setState; window.dispatchAvatarState = nextState => window.dispatchEvent(new CustomEvent('avatar-state', { detail: { state: nextState } })); window.addEventListener('avatar-state', event => setState(event.detail?.state || event.detail));
  function enableEyeFollow() {
    window.addEventListener('mousemove', function (e) {
      const widget = document.querySelector('#assistant-avatar');
      if (!widget) return;
      const portrait = widget.querySelector('.portrait');
      const image = widget.querySelector('.portrait img');
      if (!portrait || !image) return;
      const dx = (e.clientX / window.innerWidth - 0.5) * 2;
      const dy = (e.clientY / window.innerHeight - 0.5) * 2;
      portrait.style.transform = 'translate(' + (dx * 5).toFixed(1) + 'px,' + (dy * 3).toFixed(1) + 'px)';
      const state = widget.dataset.state || 'idle';
      if (state === 'speaking') return;
      const dirX = dx < -0.15 ? 'left' : dx > 0.15 ? 'right' : 'center';
      const dirY = dy < -0.15 ? 'up' : dy > 0.15 ? 'down' : 'center';
      const key = dirX === 'center' && dirY === 'center' ? 'look_center'
        : dirX === 'left' && dirY === 'up' ? 'look_upper_left'
        : dirX === 'right' && dirY === 'up' ? 'look_upper_right'
        : dirX === 'left' && dirY === 'down' ? 'look_lower_left'
        : dirX === 'right' && dirY === 'down' ? 'look_lower_right'
        : dirY === 'up' ? 'look_up'
        : dirY === 'down' ? 'look_down'
        : dirX === 'left' ? 'look_left'
        : dirX === 'right' ? 'look_right'
        : 'look_center';
      if (image.getAttribute('src') !== eyeFrames[key]) image.src = eyeFrames[key];
    });
  }
  document.addEventListener('DOMContentLoaded', () => { create(); enableEyeFollow(); setTimeout(() => { setState('listening'); settleTimer = setTimeout(() => setState('idle'), 1200); }, 180); });
})();
