(() => {
  const labels = {
    idle: '准备就绪',
    listening: '正在聆听',
    thinking: '正在思考',
    speaking: '正在回答',
    happy: '已完成',
    interrupted: '已暂停'
  };

  const portraits = {
    idle: '/static/assets/assistant_portrait_transparent.png',
    listening: '/static/assets/assistant_listening.png',
    thinking: '/static/assets/assistant_thinking.png',
    speaking: '/static/assets/assistant_speaking.png',
    happy: '/static/assets/assistant_happy.png',
    interrupted: '/static/assets/assistant_portrait_transparent.png'
  };

  const eyeFrameRoot = '/static/assets/gaze';
  const eyeFrameCount = 24;
  const eyeStepDegrees = 360 / eyeFrameCount;
  const eyeCenterFrame = `${eyeFrameRoot}/gaze_00.png`;
  const mouthFrames = {
    closed: '/static/assets/mouth_frames/mouth_closed.png',
    half: '/static/assets/mouth_frames/mouth_half.png',
    open: '/static/assets/mouth_frames/mouth_open.png'
  };
  const mouthPattern = ['closed', 'half', 'open', 'half', 'open', 'half'];
  const positionKey = 'lab-agent-avatar-position';
  let settleTimer = null;
  let mouthTimer = null;
  let mouthPatternIndex = 0;
  let mouthFramesReady = false;
  let eyeFramesReady = false;

  const gaze = {
    targetX: 0,
    targetY: 0,
    currentX: 0,
    currentY: 0,
    initialized: false,
    pointerInside: false,
    currentFrame: 'gaze_00.png',
    candidateFrame: 'gaze_00.png',
    candidateCount: 0,
    rafId: 0,
    returnTimer: null
  };

  function clampPosition(widget, left, top) {
    const width = widget.offsetWidth || 225;
    const height = widget.offsetHeight || 310;
    return {
      left: Math.max(4, Math.min(left, window.innerWidth - width - 4)),
      top: Math.max(4, Math.min(top, window.innerHeight - height - 4))
    };
  }

  function place(widget, left, top, save = false) {
    const pos = clampPosition(widget, left, top);
    widget.style.left = `${pos.left}px`;
    widget.style.top = `${pos.top}px`;
    widget.style.right = 'auto';
    widget.style.bottom = 'auto';
    if (save) localStorage.setItem(positionKey, JSON.stringify(pos));
  }

  function restorePosition(widget) {
    try {
      const saved = JSON.parse(localStorage.getItem(positionKey));
      if (Number.isFinite(saved?.left) && Number.isFinite(saved?.top)) {
        place(widget, saved.left, saved.top);
      }
    } catch (_) {
      localStorage.removeItem(positionKey);
    }
  }

  function enableDragging(widget) {
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let originLeft = 0;
    let originTop = 0;
    let moved = false;

    widget.addEventListener('pointerdown', event => {
      if (event.button !== 0 && event.pointerType !== 'touch') return;
      const rect = widget.getBoundingClientRect();
      pointerId = event.pointerId;
      startX = event.clientX;
      startY = event.clientY;
      originLeft = rect.left;
      originTop = rect.top;
      widget.classList.add('is-dragging');
      widget.setPointerCapture?.(pointerId);
      event.preventDefault();
    });

    widget.addEventListener('pointermove', event => {
      if (event.pointerId !== pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        moved = true;
        widget.dataset.moved = '1';
      }
      place(widget, originLeft + dx, originTop + dy);
    });

    const finish = event => {
      if (event.pointerId !== pointerId) return;
      const rect = widget.getBoundingClientRect();
      place(widget, rect.left, rect.top, true);
      widget.classList.remove('is-dragging');
      pointerId = null;
      widget.dataset.moved = moved ? '1' : '';
      moved = false;
    };

    widget.addEventListener('pointerup', finish);
    widget.addEventListener('pointercancel', finish);
    window.addEventListener('resize', () => {
      const rect = widget.getBoundingClientRect();
      place(widget, rect.left, rect.top, true);
    });
  }

  function eyeFrameNameForPoint(widget, clientX, clientY) {
    const portrait = widget.querySelector('.portrait');
    const rect = portrait.getBoundingClientRect();
    const faceX = rect.left + rect.width * 0.5;
    const faceY = rect.top + rect.height * 0.31;
    const dx = clientX - faceX;
    const dy = clientY - faceY;
    const deadZone = Math.max(34, rect.width * 0.16);

    if (Math.hypot(dx, dy) < deadZone) return 'look_center.png';

    const degrees = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
    const index = Math.round(degrees / eyeStepDegrees) % eyeFrameCount;
    return `gaze_${String(index).padStart(2, '0')}.png`;
  }

  function setEyeFrame(widget, frameName, immediate = false) {
    if (!eyeFramesReady) return;

    if (!immediate && frameName !== gaze.currentFrame) {
      if (frameName !== gaze.candidateFrame) {
        gaze.candidateFrame = frameName;
        gaze.candidateCount = 1;
        return;
      }
      gaze.candidateCount += 1;
      if (gaze.candidateCount < 2) return;
    }

    gaze.currentFrame = frameName;
    gaze.candidateFrame = frameName;
    gaze.candidateCount = 0;

    const image = widget.querySelector('.avatar-eyes');
    const src = `${eyeFrameRoot}/${frameName}`;
    if (image.getAttribute('src') !== src) image.src = src;
    image.hidden = false;
  }

  function returnEyesToCenter(widget) {
    clearTimeout(gaze.returnTimer);
    gaze.returnTimer = setTimeout(() => {
      gaze.pointerInside = false;
      setEyeFrame(widget, 'gaze_00.png', true);
    }, 360);
  }

  function startEyeTracking(widget) {
    window.addEventListener('pointermove', event => {
      if (event.pointerType === 'touch') return;
      clearTimeout(gaze.returnTimer);
      gaze.targetX = event.clientX;
      gaze.targetY = event.clientY;
      gaze.pointerInside = true;
      if (!gaze.initialized) {
        gaze.currentX = event.clientX;
        gaze.currentY = event.clientY;
        gaze.initialized = true;
      }
    }, { passive: true });

    document.documentElement.addEventListener('mouseleave', () => returnEyesToCenter(widget));
    window.addEventListener('blur', () => returnEyesToCenter(widget));
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) returnEyesToCenter(widget);
    });

    const tick = () => {
      gaze.rafId = requestAnimationFrame(tick);
      if (!eyeFramesReady || !gaze.initialized || !gaze.pointerInside) return;
      if (widget.classList.contains('is-dragging')) return;

      const smoothing = 0.22;
      gaze.currentX += (gaze.targetX - gaze.currentX) * smoothing;
      gaze.currentY += (gaze.targetY - gaze.currentY) * smoothing;
      setEyeFrame(widget, eyeFrameNameForPoint(widget, gaze.currentX, gaze.currentY));
    };

    gaze.rafId = requestAnimationFrame(tick);
  }

  function preloadEyeFrames(widget) {
    const eyeLayer = widget.querySelector('.avatar-eyes');
    const center = new Image();
    center.onload = () => {
      eyeLayer.src = eyeCenterFrame;
      eyeLayer.hidden = false;

      let settled = 0;
      let failed = false;
      const finish = success => {
        settled += 1;
        failed ||= !success;
        if (settled === eyeFrameCount) eyeFramesReady = !failed;
      };

      for (let index = 0; index < eyeFrameCount; index += 1) {
        const image = new Image();
        image.onload = () => finish(true);
        image.onerror = () => finish(false);
        image.src = `${eyeFrameRoot}/gaze_${String(index).padStart(2, '0')}.png`;
      }
    };
    center.onerror = () => {
      eyeFramesReady = false;
      eyeLayer.hidden = true;
    };
    center.src = eyeCenterFrame;
  }

  function preloadMouthFrames() {
    const entries = Object.entries(mouthFrames);
    let loaded = 0;
    let failed = false;

    entries.forEach(([, src]) => {
      const image = new Image();
      image.onload = () => {
        loaded += 1;
        if (!failed && loaded === entries.length) {
          mouthFramesReady = true;
          const widget = document.querySelector('#assistant-avatar');
          if (widget?.classList.contains('is-speaking')) startMouthAnimation(widget);
        }
      };
      image.onerror = () => {
        failed = true;
        mouthFramesReady = false;
      };
      image.src = src;
    });
  }

  function stopMouthAnimation(widget) {
    clearTimeout(mouthTimer);
    mouthTimer = null;
    mouthPatternIndex = 0;
    const mouth = widget.querySelector('.avatar-mouth');
    if (mouth) mouth.hidden = true;
  }

  function startMouthAnimation(widget) {
    stopMouthAnimation(widget);
    if (!mouthFramesReady) return;

    const mouth = widget.querySelector('.avatar-mouth');
    const advance = () => {
      if (!widget.classList.contains('is-speaking')) {
        stopMouthAnimation(widget);
        return;
      }

      const key = mouthPattern[mouthPatternIndex % mouthPattern.length];
      mouthPatternIndex += 1;
      const src = mouthFrames[key];
      if (mouth.getAttribute('src') !== src) mouth.src = src;
      mouth.hidden = false;
      mouthTimer = setTimeout(advance, 95 + Math.round(Math.random() * 45));
    };

    advance();
  }

  function create() {
    if (document.querySelector('#assistant-avatar')) return;

    const style = document.createElement('style');
    style.textContent = `
      #assistant-avatar{position:fixed;right:18px;bottom:72px;z-index:25;width:225px;background:transparent;user-select:none;touch-action:none;cursor:grab;filter:drop-shadow(0 12px 14px rgba(32,58,107,.22));transition:filter .2s ease}
      #assistant-avatar.is-dragging{cursor:grabbing;filter:drop-shadow(0 17px 20px rgba(32,58,107,.3))}
      #assistant-avatar .portrait{position:relative;width:100%;height:278px;overflow:visible;pointer-events:none}
      #assistant-avatar .avatar-visual{position:absolute;inset:0;transform-origin:50% 88%;animation:avatarBreathe 3.2s ease-in-out infinite}
      #assistant-avatar .avatar-layer{position:absolute;inset:0;display:block;width:100%;height:100%;object-fit:contain;object-position:center bottom;pointer-events:none;transition:none}
      #assistant-avatar .avatar-eyes,#assistant-avatar .avatar-mouth{z-index:1}
      #assistant-avatar .avatar-info{display:flex;align-items:center;justify-content:center;gap:7px;width:max-content;min-height:29px;margin:-4px auto 0;padding:5px 11px;border:1px solid rgba(88,128,204,.3);border-radius:999px;background:rgba(255,253,248,.88);box-shadow:0 4px 15px rgba(37,66,122,.14);color:#25477e;font-size:12px;backdrop-filter:blur(6px);pointer-events:none}
      #assistant-avatar .avatar-name{font-weight:800;color:#193d78}
      #assistant-avatar .avatar-dot{display:inline-block;width:7px;height:7px;margin-right:4px;border-radius:50%;background:#83a3d8}
      #assistant-avatar .avatar-thought{position:absolute;z-index:2;top:10px;right:0;display:none;min-width:34px;max-width:210px;padding:7px 10px;border-radius:14px;background:rgba(255,255,255,.96);border:1px solid rgba(88,128,204,.16);color:#5473ac;font-weight:600;letter-spacing:0;line-height:1.55;white-space:pre-wrap;word-break:break-word;text-align:left;box-shadow:0 6px 18px rgba(42,71,126,.18);pointer-events:none}
      #assistant-avatar.is-listening .avatar-dot{background:#40a576;box-shadow:0 0 0 5px rgba(64,165,118,.15);animation:avatarPulse 1s infinite}
      #assistant-avatar.is-thinking .avatar-dot{background:#e0a241;animation:avatarBlink .75s infinite}
      #assistant-avatar.is-thinking .avatar-thought{display:block;animation:avatarThought 1s ease-in-out infinite}
      #assistant-avatar.is-speaking .avatar-visual{animation:avatarTalk .34s ease-in-out infinite alternate}
      #assistant-avatar.is-speaking .avatar-dot{background:#4d83e9;animation:avatarPulse .7s infinite}
      #assistant-avatar.is-happy .avatar-dot{background:#e3816c}
      #assistant-avatar.is-interrupted .avatar-visual{filter:grayscale(.22) saturate(.78)}
      #assistant-avatar.is-interrupted .avatar-dot{background:#a98563}
      @keyframes avatarBreathe{50%{transform:translateY(-3px) scale(1.012)}}
      @keyframes avatarTalk{to{transform:translateY(-3px) scale(1.015)}}
      @keyframes avatarPulse{50%{transform:scale(1.35);box-shadow:0 0 0 8px rgba(64,130,226,.07)}}
      @keyframes avatarBlink{50%{opacity:.2}}
      @keyframes avatarThought{50%{transform:translateY(-3px);opacity:.65}}
      @media(prefers-reduced-motion:reduce){#assistant-avatar .avatar-visual,#assistant-avatar .avatar-dot,#assistant-avatar .avatar-thought{animation-duration:1ms!important;animation-iteration-count:1!important}}
      @media(max-width:720px){#assistant-avatar{right:4px;bottom:61px;width:150px}#assistant-avatar .portrait{height:187px}#assistant-avatar .avatar-info{min-height:25px;padding:4px 8px;font-size:10px}}
    `;
    document.head.appendChild(style);

    const widget = document.createElement('aside');
    widget.id = 'assistant-avatar';
    widget.className = 'is-idle';
    widget.setAttribute('aria-label', '可拖动的实验助手虚拟形象');
    widget.innerHTML = `
      <div class="portrait">
        <div class="avatar-visual">
          <img class="avatar-layer avatar-base" src="${portraits.idle}" alt="小科实验助手">
          <img class="avatar-layer avatar-eyes" src="${eyeCenterFrame}" alt="" aria-hidden="true" hidden>
          <img class="avatar-layer avatar-mouth" alt="" aria-hidden="true" hidden>
        </div>
        <span class="avatar-thought">···</span>
      </div>
      <div class="avatar-info"><span class="avatar-name">小科</span><span><i class="avatar-dot"></i><span class="avatar-label">准备就绪</span></span></div>
    `;

    document.body.appendChild(widget);
    Object.values(portraits).forEach(src => {
      const image = new Image();
      image.src = src;
    });

    restorePosition(widget);
    enableDragging(widget);
    preloadEyeFrames(widget);
    preloadMouthFrames();
    startEyeTracking(widget);

    widget.addEventListener('click', () => {
      if (widget.dataset.moved !== '1' && window.phoneCallToggle) window.phoneCallToggle();
    });
  }

  function setState(nextState) {
    if (!labels[nextState]) nextState = 'idle';
    const widget = document.querySelector('#assistant-avatar');
    if (!widget) return;

    const dragging = widget.classList.contains('is-dragging');
    widget.className = `is-${nextState}${dragging ? ' is-dragging' : ''}`;
    widget.querySelector('.avatar-label').textContent = labels[nextState];

    const image = widget.querySelector('.avatar-base');
    if (image.getAttribute('src') !== portraits[nextState]) image.src = portraits[nextState];

    if (nextState === 'speaking') startMouthAnimation(widget);
    else stopMouthAnimation(widget);

    clearTimeout(settleTimer);
  }

  window.setAvatarState = setState;
  window.dispatchAvatarState = nextState => window.dispatchEvent(new CustomEvent('avatar-state', { detail: { state: nextState } }));
  window.addEventListener('avatar-state', event => setState(event.detail?.state || event.detail));

  document.addEventListener('DOMContentLoaded', () => {
    create();
    setTimeout(() => {
      setState('listening');
      settleTimer = setTimeout(() => setState('idle'), 1200);
    }, 180);
  });
})();
