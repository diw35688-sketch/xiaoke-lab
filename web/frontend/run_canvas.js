// 工作画布：实验进行中的可视化主区。
// 参考 deepseek-harness：
//   - 工具调用用 presentCall/presentResult 卡片，调用前先出待执行卡
//   - 步骤时间线在顶部，当前步高亮
(function () {
  var CSS = [
    '#rc{max-width:860px;margin:0 auto}',
    // 步骤时间线：紧凑一行，不再是大方块
    '#rc-steps{display:flex;gap:4px;overflow-x:auto;padding:0 0 12px;align-items:center}',
    '.rc-step{flex:0 0 auto;display:flex;align-items:center;gap:6px;background:var(--n-00);border:1px solid var(--bd-2);border-radius:999px;padding:4px 11px 4px 5px;cursor:pointer;font-size:var(--fs-sm);color:var(--n-700);white-space:nowrap}',
    '.rc-step:hover{border-color:var(--bd-3)}',
    '.rc-step.cur{border-color:var(--brand);color:var(--brand-strong);background:var(--brand-50)}',
    '.rc-step.done{color:var(--n-500)}',
    '.rc-sn{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;background:var(--n-200);color:var(--n-700);font-size:10px;font-weight:600;flex:0 0 17px}',
    '.rc-step.cur .rc-sn{background:var(--brand);color:#fff}',
    '.rc-step.done .rc-sn{background:var(--green-500);color:#fff}',
    '.rc-step.pending .rc-sn{background:#d97706;color:#fff}',
      '.rc-progress{height:6px;background:var(--n-100);border-radius:999px;overflow:hidden;margin:0 0 6px}',
      '.rc-progress-bar{height:100%;background:var(--brand);border-radius:999px;transition:width .25s ease}',
      '.rc-progress-text{font-size:var(--fs-xs);color:var(--n-500);margin-bottom:12px}',
    // 卡片：一个大步骤 + 其小步骤
    '.rc-card{background:var(--n-00);border:1px solid var(--bd-2);border-radius:var(--r-lg);margin-bottom:10px;overflow:hidden}',
    '.rc-card-h{padding:12px 15px;display:flex;align-items:flex-start;gap:10px;border-bottom:1px solid var(--bd-1)}',
    '.rc-card-h.plain{border-bottom:0}',
    '.rc-badge{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 6px;border-radius:var(--r-sm);background:var(--brand-50);color:var(--brand-strong);font-size:var(--fs-xs);font-weight:600;margin-top:1px}',
    '.rc-hmain{flex:1;min-width:0}',
    '.rc-t{font-size:var(--fs-lg);font-weight:600;color:var(--n-900);line-height:1.4}',
    '.rc-sub{font-size:var(--fs-sm);color:var(--n-600);margin-top:3px;line-height:1.6}',
    '.rc-body{padding:12px 15px}',
    // 小步骤列表
    '.rc-sub-item{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--bd-1)}',
    '.rc-sub-item:last-child{border-bottom:0}',
    '.rc-sub-n{flex:0 0 18px;height:18px;border-radius:50%;border:1px solid var(--bd-3);color:var(--n-600);font-size:10px;display:inline-flex;align-items:center;justify-content:center;margin-top:1px}',
    '.rc-sub-c{flex:1;min-width:0}',
    '.rc-sub-t{font-size:var(--fs-md);color:var(--n-900);line-height:1.6}',
    '.rc-kv{display:inline-block;background:var(--n-75);color:var(--n-700);border-radius:var(--r-sm);padding:2px 7px;margin:4px 5px 0 0;font-size:var(--fs-xs)}',
    '.rc-kv.rec{background:var(--amber-100);color:var(--amber-600)}',
    '.rc-lbl{font-size:var(--fs-xs);color:var(--n-500);margin:12px 0 4px}',
    '.rc-lbl:first-child{margin-top:0}',
    // 安全条
    '.rc-safe{border:1px solid var(--bd-2);border-left:2px solid var(--red-500);background:var(--red-50);border-radius:var(--r-md);padding:10px 13px;margin-bottom:10px}',
    '.rc-safe.mild{border-left-color:var(--green-500);background:var(--green-100)}',
    '.rc-safe b{color:var(--red-600);display:block;margin-bottom:3px;font-size:var(--fs-md);font-weight:600}',
    '.rc-safe.mild b{color:var(--green-900)}',
    '.rc-safe div{color:var(--n-800);font-size:var(--fs-sm);line-height:1.65}',
    '.rc-safe small{color:var(--n-500);font-size:var(--fs-xs);display:block;margin-top:5px}',
    // 思维链
    '.rc-think{margin-bottom:1px;overflow:hidden}','.rc-think-row .dot,.rc-tool-h .dot{color:rgba(0,0,0,.2);flex:0 0 auto}',
    '.rc-think-row{display:flex;align-items:center;gap:7px;padding:5px 2px;cursor:pointer;position:relative;overflow:hidden}',
    '.rc-think-row .ic{font-size:11px;color:var(--n-500);flex:0 0 auto}',
    '.rc-think-row .tt{font-size:var(--fs-sm);font-weight:500;color:var(--n-800);flex:0 0 auto}',
    '.rc-think-row .sep{width:1px;height:11px;background:var(--bd-2);flex:0 0 auto}',
    '.rc-think-row .sm{font-size:var(--fs-sm);color:var(--n-600);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}',
    '.rc-think-row .cv{color:var(--n-400);font-size:var(--fs-xs);flex:0 0 auto}',
    '.rc-think.running .rc-think-row::after{content:"";position:absolute;inset-block:0;left:-260px;width:260px;background:linear-gradient(90deg,transparent,rgba(0,0,0,.035),transparent);animation:rcsweep 2.6s ease-out infinite;pointer-events:none}',
    '@keyframes rcsweep{0%{left:-260px}90%,100%{left:100%}}',
    '.rc-think-body{margin:2px 0 8px 22px;padding:9px 12px;background:var(--n-60);border-radius:var(--r-md);color:var(--n-700);font-size:var(--fs-sm);line-height:1.75;white-space:pre-wrap;display:none}',
    '.rc-think.open .rc-think-body{display:block}',
    // 工具卡片
    '.rc-tool{margin-bottom:1px}','.rc-name{font-weight:500;color:var(--n-800);flex:0 0 auto}','.rc-sum{color:var(--n-600);font-size:var(--fs-sm);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}',

    '.rc-tool.error .rc-name{color:var(--red-600)}',
    '.rc-tool-h{display:flex;align-items:center;gap:7px;font-size:var(--fs-md);padding:5px 2px;min-width:0}',
    '.rc-ic{width:15px;text-align:center;font-size:12px;color:var(--n-500);flex:0 0 15px}',
    '.rc-ic.read{background:var(--brand-50);color:var(--brand-strong)}',
    '.rc-ic.execute{background:var(--brand-100);color:var(--brand-strong)}',
    '.rc-state{margin-left:auto;font-size:var(--fs-xs);font-weight:400;color:var(--n-500)}',
    '.rc-tool-b{margin:2px 0 8px 22px;padding:9px 12px;background:var(--n-60);border-radius:var(--r-md);color:var(--n-700);font-size:var(--fs-sm);line-height:1.7}',
    '.rc-tool-b .warn{color:var(--red-600)}',
    '.rc-spin{display:inline-block;width:9px;height:9px;border:1.5px solid var(--brand-100);border-top-color:var(--brand);border-radius:50%;animation:rcspin .7s linear infinite}',
    '@keyframes rcspin{to{transform:rotate(360deg)}}',
    '.rc-sec-title{font-size:var(--fs-xs);color:var(--n-500);margin:16px 0 7px;display:flex;align-items:center;gap:8px}',
    '.rc-sec-title::after{content:"";flex:1;height:1px;background:var(--bd-1)}',
    // 实验前准备清单
    '.rc-prep{background:var(--n-00);border:1px solid var(--bd-2);border-radius:var(--r-lg);margin-bottom:10px;overflow:hidden}',
    '.rc-prep-h{padding:11px 15px;font-weight:600;color:var(--n-900);font-size:var(--fs-md);border-bottom:1px solid var(--bd-1);display:flex;justify-content:space-between;align-items:center;gap:8px}',
    '.rc-prep-item{display:flex;gap:8px;align-items:center;padding:8px 12px;border-bottom:1px dashed var(--bd-1);font-size:var(--fs-sm);color:var(--n-800)}',
    '.rc-prep-item:last-child{border-bottom:0}',
    '.rc-prep-item.have{color:var(--n-500);background:var(--green-100)}',
    '.rc-prep-item .rc-prep-name{flex:1;min-width:0}',
    '.rc-prep-btn{flex:0 0 auto;border:1px solid var(--bd-2);background:#fff;border-radius:999px;padding:3px 10px;font-size:12px;cursor:pointer;color:var(--n-700)}',
    '.rc-prep-btn.have:hover{border-color:var(--green-500);color:var(--green-700)}',
    '.rc-prep-btn.missing:hover{border-color:var(--amber-500);color:var(--amber-700)}',
    '.rc-prep-item.have .rc-prep-btn{opacity:.55}',
    '.rc-prep-item.insuf{background:var(--amber-50,#fffbeb)}',
    // 新记录到达时的闪烁高亮（SSE 推送触发）
    '@keyframes nbflash{0%{box-shadow:0 0 0 0 rgba(37,99,235,.5)}30%{box-shadow:0 0 0 6px rgba(37,99,235,.25)}100%{box-shadow:0 0 0 0 transparent}}',
    '.nb-flash{animation:nbflash 1.2s ease-out 2}',
    // 剪映式时间轴：横轴=时间，纵轴=轨道（每行一个实验）
    '.rc-tl-wrap{background:var(--n-00);border:1px solid var(--bd-2);border-radius:var(--r-lg);margin-bottom:14px}',
    '.rc-tl-scroll{overflow-x:auto;overflow-y:hidden}',
    '.rc-tl-scroll::-webkit-scrollbar{height:6px}',
    '.rc-tl-scroll::-webkit-scrollbar-thumb{background:var(--bd-2);border-radius:3px}',
    '.rc-tl-inner{position:relative;min-width:max-content}',
    // 左侧轨道名固定列
    '.rc-tl-label-col{position:sticky;left:0;z-index:6;width:110px;flex:0 0 110px;background:var(--n-00)}',
    // 顶部时间标尺
    '.rc-tl-ruler{display:flex;height:34px;border-bottom:2px solid var(--bd-2);background:var(--n-50);position:sticky;top:0;z-index:5}',
    '.rc-tl-ruler-label{width:110px;flex:0 0 110px;border-right:1px solid var(--bd-2);display:flex;align-items:center;padding-left:10px;font-size:11px;color:var(--n-500);background:var(--n-50);position:sticky;left:0;z-index:6}',
    '.rc-tl-ticks{position:relative;flex:1;height:34px}',
    '.rc-tl-tick{position:absolute;top:0;bottom:0;border-left:1px solid var(--bd-1);font-size:10px;color:var(--n-400);padding-left:3px;line-height:34px;white-space:nowrap}',
    '.rc-tl-tick .pd{display:inline-block;font-size:9px;font-weight:700;color:#fff;padding:1px 5px;border-radius:4px;margin-right:4px;transform:translateY(-1px)}',
    // 轨道行
    '.rc-tl-row{display:flex;border-bottom:1px solid var(--bd-1);position:relative;min-height:46px}',
    '.rc-tl-row:last-child{border-bottom:0}',
    '.rc-tl-row.active{background:rgba(59,103,232,.025)}',
    '.rc-tl-row-label{width:110px;flex:0 0 110px;border-right:1px solid var(--bd-2);display:flex;align-items:center;gap:3px;padding-left:10px;position:sticky;left:0;z-index:4;background:inherit}',
    '.rc-tl-row-label.active{background:var(--brand-50)}',
    '.rc-tl-row-name{font-size:12px;font-weight:600;color:var(--n-900);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '.rc-tl-row-prog{font-size:9px;color:var(--n-500);flex:0 0 auto}',
    '.rc-tl-row-x{width:18px;height:18px;border:0;border-radius:50%;background:transparent;font-size:11px;color:var(--n-400);cursor:pointer;flex:0 0 18px;padding:0;line-height:1}',
    '.rc-tl-row-x:hover{background:var(--red-50);color:var(--red-500)}',
    // 轨道时间区域
    '.rc-tl-track{position:relative;flex:1;min-height:46px}',
    '.rc-tl-grid-h{position:absolute;top:0;bottom:0;border-left:1px dashed var(--bd-1)}',
    // 步骤块（按 left 定位）
    '.rc-tl-step{position:absolute;top:5px;height:36px;border-radius:7px;padding:3px 7px;cursor:pointer;transition:transform .12s,box-shadow .12s;overflow:hidden;font-size:11px;line-height:1.3;border:1px solid transparent;display:flex;align-items:center;gap:3px;white-space:nowrap}',
    '.rc-tl-step:hover{transform:translateY(-1px);box-shadow:0 3px 8px rgba(0,0,0,.15);z-index:5}',
    '.rc-tl-step.done{background:var(--green-100);border-color:var(--green-300);color:var(--green-900)}',
    '.rc-tl-step.cur{background:var(--brand);border-color:var(--brand-strong);color:#fff;font-weight:600;box-shadow:0 0 0 2px rgba(59,103,232,.2)}',
    '.rc-tl-step.pending{background:var(--n-75);border-color:var(--bd-1);color:var(--n-500)}',
    '.rc-tl-step.planned{background:var(--blue-50);border-color:var(--blue-200);color:var(--blue-700);border-style:dashed;opacity:.75}',
    '.rc-tl-row.planned-row .rc-tl-row-label{color:var(--blue-700);font-style:normal}',
    '.rc-tl-row.planned-row{background:var(--blue-50)}',
    '.rc-tl-step-n{font-size:9px;opacity:.65;flex:0 0 auto}',
    // 休息区（竖向条纹列）
    '.rc-tl-break{position:absolute;top:0;bottom:0;background:repeating-linear-gradient(135deg,#f1f5f9,#f1f5f9 6px,#e2e8f0 6px,#e2e8f0 12px);z-index:1;display:flex;align-items:flex-start;justify-content:center;padding-top:2px}',
    '.rc-tl-break-label{font-size:9px;color:var(--n-400);writing-mode:vertical-rl;text-orientation:upright;letter-spacing:1px}',
    // 现在时间线（竖向红线）
    '.rc-tl-now{position:absolute;top:0;bottom:0;width:0;border-left:2px solid var(--red-500);z-index:4;pointer-events:none}',
    '.rc-tl-now-label{position:absolute;top:0;left:2px;font-size:9px;color:var(--red-500);background:var(--n-00);padding:0 3px;white-space:nowrap}',
    // 底部添加按钮行
    '.rc-tl-addrow{display:flex;align-items:center;padding:6px 10px;border-top:1px solid var(--bd-2);cursor:pointer;color:var(--n-400);font-size:13px;gap:5px}',
    '.rc-tl-addrow:hover{background:var(--brand-50);color:var(--brand)}'
  ].join('');

  var session = null;
  var records = null;
  var checklist = null;
  var prepBench = null;
  var reagentPrepList = [];
  var checklistState = {};
  var activeTracks = []; // 多轨道：所有进行中的实验

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }
  function api(path, method, payload) {
    var options = { method: method || 'GET' };
    if (payload) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    return fetch(path, options).then(function (r) { return r.json(); });
  }
  // 当前激活轨道的 protocol_id 和 lab_session_id
  function currentTrackId() {
    if (!session || session.mode !== 'protocol') return null;
    var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
    return { protocol_id: session.protocol.id, lab_session_id: ids.lab_session_id };
  }

  // 判断某轨道是否是当前激活的
  function isTrackActive(track) {
    var cur = currentTrackId();
    if (!cur) return false;
    return track.lab_session_id === cur.lab_session_id || track.protocol_id === cur.protocol_id;
  }

  // 剪映式时间轴：横轴=时间（08:00→22:00），纵轴=实验轨道（每行一个实验）
  var TL_HOUR_PX = 92;           // 每小时像素宽度（横向可滚动）
  var TL_START = 8;              // 08:00
  var TL_END = 22;               // 22:00
  var TL_BREAKS = [
    { start: 11.5, end: 12.5, label: '午休' },
    { start: 17,   end: 19,   label: '下班' },
  ];
  var TL_PERIODS = [
    { start: 8,    end: 11.5, label: '上午', color: '#3b67e8' },
    { start: 12.5, end: 17,   label: '下午', color: '#0891b2' },
    { start: 19,   end: 22,   label: '晚间', color: '#7c3aed' },
  ];
  var TL_LABEL_W = 110;          // 左侧轨道名列宽度

  function timeToX(hour) { return Math.round((hour - TL_START) * TL_HOUR_PX); }

  function timelineHtml() {
    if (!activeTracks || activeTracks.length === 0) return '';
    var cur = currentTrackId();
    var totalW = (TL_END - TL_START) * TL_HOUR_PX;

    // ---- 工作时间段（半小时粒度，跳过午休/下班）----
    var workSlots = [];
    for (var pi = 0; pi < TL_PERIODS.length; pi++) {
      var per = TL_PERIODS[pi];
      for (var t = per.start; t < per.end - 0.01; t += 0.5) workSlots.push(t);
    }

    // ---- 顶部时间标尺 ----
    var ticksHtml = '';
    for (var h = TL_START; h <= TL_END; h++) {
      var pdLabel = '';
      for (var pp = 0; pp < TL_PERIODS.length; pp++) {
        if (Math.abs(TL_PERIODS[pp].start - h) < 0.01) {
          pdLabel = '<span class="pd" style="background:' + TL_PERIODS[pp].color + '">' + TL_PERIODS[pp].label + '</span>';
        }
      }
      ticksHtml += '<div class="rc-tl-tick" style="left:' + timeToX(h) + 'px">'
        + pdLabel + (h < 10 ? '0' : '') + h + ':00</div>';
    }
    // 休息区标记（标尺上）
    for (var bi = 0; bi < TL_BREAKS.length; bi++) {
      var bk = TL_BREAKS[bi];
      ticksHtml += '<div class="rc-tl-break" style="left:' + timeToX(bk.start) + 'px;width:' + ((bk.end - bk.start) * TL_HOUR_PX) + 'px;height:34px">'
        + '<span class="rc-tl-break-label">' + bk.label + '</span></div>';
    }

    var rulerHtml = '<div class="rc-tl-ruler">'
      + '<div class="rc-tl-ruler-label">实验轨道</div>'
      + '<div class="rc-tl-ticks" style="width:' + totalW + 'px">' + ticksHtml + '</div>'
      + '</div>';

    // ---- 每条轨道一行 ----
    var rowsHtml = '';
    activeTracks.forEach(function (track) {
      var isActive = isTrackActive(track);
      var isPlanned = !!track.is_planned;
      var pct = track.total_steps ? Math.round((track.completed_steps / track.total_steps) * 100) : 0;
      var steps = track.steps || [];
      var nSteps = steps.length || 1;
      var slotPerStep = Math.max(1, Math.floor(workSlots.length / nSteps));
      var stepWidth = Math.round(TL_HOUR_PX * slotPerStep * 0.5) - 6;

      // 左侧轨道名
      var planBadge = isPlanned
        ? ' <span style="font-size:9px;background:var(--blue-100);color:var(--blue-600);border-radius:4px;padding:0 4px;margin-left:4px">计划</span>'
        : '';
      var progHtml = isPlanned
        ? '<span class="rc-tl-row-prog" style="color:var(--blue-500)">待启动</span>'
        : '<span class="rc-tl-row-prog">' + (track.completed_steps || 0) + '/' + (track.total_steps || 0) + '</span>';
      var closeBtn = isPlanned
        ? ''
        : '<button class="rc-tl-row-x" data-archive="' + esc(track.lab_session_id) + '" title="归档/结束">✕</button>';
      var labelHtml = '<div class="rc-tl-row-label' + (isActive ? ' active' : '"') + '"'
        + ' data-tl-protocol="' + esc(track.protocol_id) + '"'
        + ' data-tl-session="' + esc(track.lab_session_id) + '"'
        + ' data-tl-title="' + esc(track.title) + '"'
        + ' data-tl-planned="' + (isPlanned ? '1' : '') + '">'
        + '<span class="rc-tl-row-name">' + esc(track.short_title || track.title) + planBadge + '</span>'
        + progHtml
        + closeBtn
        + '</div>';

      // 右侧步骤块（按时间定位）
      var blocksHtml = '';
      // 网格竖线
      for (var gh = TL_START; gh <= TL_END; gh++) {
        blocksHtml += '<div class="rc-tl-grid-h" style="left:' + timeToX(gh) + 'px"></div>';
      }
      // 休息区
      for (var bb = 0; bb < TL_BREAKS.length; bb++) {
        var brk = TL_BREAKS[bb];
        blocksHtml += '<div class="rc-tl-break" style="left:' + timeToX(brk.start) + 'px;width:' + ((brk.end - brk.start) * TL_HOUR_PX) + 'px"></div>';
      }
      // 步骤块
      steps.forEach(function (step, idx) {
        var slotIdx = Math.min(idx * slotPerStep, workSlots.length - 1);
        var stepTime = workSlots[slotIdx] != null ? workSlots[slotIdx] : TL_START;
        var leftPx = timeToX(stepTime) + 3;
        var cls = isPlanned ? ' planned'
          : (step.status === 'completed' || step.status === 'left_with_pending') ? ' done'
          : (step.n === track.current_step ? ' cur' : ' pending');
        blocksHtml += '<div class="rc-tl-step' + cls + '"'
          + ' style="left:' + leftPx + 'px;min-width:' + Math.max(stepWidth, 44) + 'px"'
          + ' data-tl-session="' + esc(track.lab_session_id) + '"'
          + ' data-tl-protocol="' + esc(track.protocol_id) + '"'
          + ' data-tl-title="' + esc(track.title) + '"'
          + ' data-tl-step="' + step.n + '"'
          + ' data-tl-planned="' + (isPlanned ? '1' : '') + '"'
          + ' title="' + esc(track.short_title || track.title) + ' · 步骤' + step.n + ': ' + esc(step.title || '') + '">'
          + '<span class="rc-tl-step-n">' + step.n + '</span>' + esc(step.title || '')
          + '</div>';
      });

      var trackHtml = '<div class="rc-tl-track" style="width:' + totalW + 'px">' + blocksHtml + '</div>';
      rowsHtml += '<div class="rc-tl-row' + (isActive ? ' active' : '') + (isPlanned ? ' planned-row' : '') + '">'
        + labelHtml + trackHtml + '</div>';
    });

    // ---- "现在"竖线（放在 .rc-tl-inner 内部，跟随横向滚动）----
    var nowHtml = '';
    var now = new Date();
    var nowHour = now.getHours() + now.getMinutes() / 60;
    if (nowHour >= TL_START && nowHour <= TL_END) {
      var nowX = timeToX(nowHour) + TL_LABEL_W;  // 加上左侧标签列宽
      nowHtml = '<div class="rc-tl-now" style="left:' + nowX + 'px;top:34px;bottom:0">'
        + '<div class="rc-tl-now-label">现在 ' + ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) + '</div></div>';
    }

    // ---- 添加实验行 ----
    var addRowHtml = '<div class="rc-tl-addrow" id="rc-tl-add-btn">＋ 添加实验</div>';

    return '<div class="rc-tl-wrap"><div class="rc-tl-scroll"><div class="rc-tl-inner" style="position:relative">'
      + rulerHtml + rowsHtml + nowHtml
      + '</div></div>' + addRowHtml + '</div>';
  }

  function stepsHtml() {
    if (!session || session.mode !== 'protocol' || !session.all_steps) return '';
    var cur = session.step.number;
    return '<div id="rc-steps">' + session.all_steps.map(function (s) {
      var status = (session.step_statuses || {})[String(s.number)];
      var cls = s.number === cur ? ' cur'
        : (status === 'completed' ? ' done'
        : (status === 'left_with_pending' ? ' pending' : ''));
      return '<div class="rc-step' + cls + '" data-n="' + s.number + '">'
        + '<span class="rc-sn">' + s.number + '</span>'
        + esc(s.title)
        + (status === 'left_with_pending' ? '<span style="color:#b45309;font-size:var(--fs-xs)">·有暂缓问题</span>' : '')
        + (s.substep_count ? '<span style="color:var(--n-400);font-size:var(--fs-xs)">·' + s.substep_count + '</span>' : '') + '</div>';
    }).join('') + '</div>';
  }

  function stepCardHtml() {
    if (!session) return '';
    if (session.mode !== 'protocol') {
      return '<div class="rc-card"><div class="rc-t">自由记录模式</div>'
        + '<p class="rc-p">未选择实验方案，系统只做记录，不产生方案性追问与安全提示。'
        + '到左侧「实验方案」可选择一份。</p></div>';
    }
    var s = session.step;
    var planned = Object.keys(s.protocol_values).map(function (k) {
      return '<span class="rc-kv">' + esc(k) + ' = ' + esc(s.protocol_values[k]) + '</span>';
    }).join('') || '<span style="color:#94a3b8;font-size:12px">无</span>';
    var must = s.must_record.map(function (k) {
      return '<span class="rc-kv rec">' + esc(k) + '</span>';
    }).join('') || '<span style="color:#94a3b8;font-size:12px">无</span>';
    var safety = (session.safety || []).map(function (r) {
      var danger = r.critical;
      return '<div class="rc-safe' + (danger ? '' : ' mild') + '">'
        + '<b>' + (danger ? '高危试剂：' : '涉及试剂：') + esc(r.name)
        + (r.cas ? '（CAS ' + esc(r.cas) + '）' : '') + '</b>'
        + (danger ? r.statements.map(function (t) { return '<div>· ' + esc(t) + '</div>'; }).join('')
                  : '<div>无高危项</div>')
        + '<small>' + (danger && r.codes.length ? 'GHS ' + r.codes.join('/') + '　' : '')
        + esc(session.safety_note || '') + '</small></div>';
    }).join('');
    // 一个大步骤 + 它的小步 = 一张卡片
    var subs = (s.substeps || []).map(function (x) {
      return '<div class="rc-sub-item"><div class="rc-sub-n">' + x.order + '</div>'
        + '<div class="rc-sub-c"><div class="rc-sub-t">' + esc(x.text) + '</div>'
        + (x.note ? '<div style="color:var(--amber-600);font-size:var(--fs-xs);margin-top:3px">' + esc(x.note) + '</div>' : '')
        + '</div></div>';
    }).join('');
    var pct = Math.round((s.number / session.protocol.total_steps) * 100);
      var progress = '<div class="rc-progress"><div class="rc-progress-bar" style="width:' + pct + '%"></div></div>'
        + '<div class="rc-progress-text">步骤 ' + s.number + ' / ' + session.protocol.total_steps + ' · 完成 ' + pct + '%</div>';
      return progress + safety
      + (s.hazard_note ? '<div class="rc-safe mild"><b>方案自带提示</b><div>' + esc(s.hazard_note) + '</div></div>' : '')
      + '<div class="rc-card">'
      + '<div class="rc-card-h' + (subs ? '' : ' plain') + '">'
      + '<span class="rc-badge">' + s.number + '</span>'
      + '<div class="rc-hmain"><div class="rc-t">' + esc(s.title) + '</div>'
      + '<div class="rc-sub">' + esc(s.instruction) + '</div></div>'
      + '<button class="sh-btn" id="rc-edit" style="flex:0 0 auto">编辑</button></div>'
      + (subs ? '<div class="rc-body" style="padding-bottom:4px">' + subs + '</div>' : '')
      + '<div class="rc-body" style="border-top:1px solid var(--bd-1)">'
      + '<div class="rc-lbl">方案已定（不会追问）</div><div>' + planned + '</div>'
      + '<div class="rc-lbl">现场必测（缺了会追问）</div><div>' + must + '</div>'
      + '<div style="display:flex;gap:7px;margin-top:13px">'
      + '<button class="sh-btn" id="rc-prev">上一步</button>'
      + '<button class="sh-btn primary" id="rc-next">下一步</button></div></div></div>';
  }

  function checklistItems() {
    if (!checklist) return [];
    var items = [];
    (checklist.reagents || []).forEach(function (r) {
      items.push({key: 'reagent:' + r.name, name: r.name, kind: '试剂', found: !!r.found_in_storage, prep: findPrepForName(r.name)});
    });
    (checklist.equipment || []).forEach(function (name) {
      items.push({key: 'equipment:' + name, name: name, kind: '仪器', found: false});
    });
    (checklist.consumables || []).forEach(function (name) {
      items.push({key: 'consumable:' + name, name: name, kind: '耗材', found: false});
    });
    (checklist.prep_requirements || []).forEach(function (p) {
      var name = p.name_zh || p.name || '';
      items.push({key: 'prep:' + name, name: name, kind: '需配制', found: false, prep: p});
    });
    return items;
  }

  function findPrepForName(name) {
    var norm = String(name || '').replace(/\s+/g, '').toLowerCase();
    for (var i = 0; i < reagentPrepList.length; i++) {
      var p = reagentPrepList[i];
      var pn = String(p.name_zh || '').replace(/\s+/g, '').toLowerCase();
      if (pn && (pn === norm || pn.indexOf(norm) >= 0 || norm.indexOf(pn) >= 0)) return p;
    }
    return null;
  }

  function checklistStateKey() {
    return 'lab-prep-checklist-' + (session && session.protocol ? session.protocol.id : 'none');
  }

  function loadChecklistState() {
    try {
      var raw = localStorage.getItem(checklistStateKey());
      checklistState = raw ? JSON.parse(raw) : {};
    } catch (e) { checklistState = {}; }
  }

  function saveChecklistState() {
    try { localStorage.setItem(checklistStateKey(), JSON.stringify(checklistState)); } catch (e) {}
  }

  function checklistHtml() {
    if (!session || session.mode !== 'protocol' || !checklist) return '';
    loadChecklistState();
    var items = checklistItems();
    if (!items.length) return '';
    var rows = items.map(function (item) {
      var state = checklistState[item.key] || (item.found ? 'have' : '');
      var cls = state === 'have' ? ' have' : '';
      var mark = state === 'have' ? '✅' : '☐';
      return '<div class="rc-prep-item' + cls + '" data-key="' + esc(item.key) + '">'
        + '<span style="flex:0 0 auto">' + mark + '</span>'
        + '<span class="rc-prep-name">' + esc(item.name)
        + (item.kind ? '<span style="color:var(--n-400);font-size:11px;margin-left:6px">' + esc(item.kind) + '</span>' : '')
        + '</span>'
        + '<button class="rc-prep-btn have" data-action="have">有</button>'
        + '<button class="rc-prep-btn missing" data-action="missing">没有，去配</button>'
        + '</div>';
    }).join('');
    return '<div class="rc-sec-title">实验前准备清单</div>'
      + '<div class="rc-prep"><div class="rc-prep-h"><span>请逐项确认</span><span style="color:var(--n-400);font-size:12px">点“有”打勾；点“没有”进入配制</span></div>'
      + rows + '</div>';
  }

  var _pbSensitivity = { prechill: '需预冷', overnight: '需过夜', fresh: '现配现用' };
  var _pbStateIcon = { ready: '✅', prep_now: '🔬', missing: '⚠️', insufficient: '🔶' };
  var _pbKindLabel = { reagent: '试剂', equipment: '仪器', consumable: '耗材', prep: '需配制' };

  function prepBenchHtml() {
    if (!prepBench || !prepBench.items || !prepBench.items.length) return '';
    var s = prepBench.summary || {};
    var rows = prepBench.items.map(function (it) {
      var icon = _pbStateIcon[it.state] || '☐';
      var cls = it.state === 'ready' ? ' have' : (it.state === 'insufficient' ? ' insuf' : '');
      var qty = it.quantity ? '<span style="color:var(--n-600);font-size:12px;margin-left:4px">' + esc(it.quantity) + '</span>' : '';
      var mins = it.estimated_minutes ? '<span style="color:var(--n-500);font-size:11px;margin-left:4px">约' + it.estimated_minutes + '分钟</span>' : '';
      var tag = _pbSensitivity[it.time_sensitivity] || '';
      var tagColor = it.time_sensitivity === 'overnight' ? 'var(--red-100),var(--red-600)'
        : it.time_sensitivity === 'prechill' ? 'var(--blue-100),var(--blue-600)'
        : it.time_sensitivity === 'fresh' ? 'var(--amber-100),var(--amber-600)' : '';
      var tagHtml = tag && tagColor ? '<span style="background:' + tagColor.split(',')[0] + ';color:' + tagColor.split(',')[1] + ';font-size:10px;padding:1px 5px;border-radius:4px;margin-left:4px">' + esc(tag) + '</span>' : '';
      var kind = _pbKindLabel[it.kind] || '';
      var storageHtml = '';
      if (it.storage_hint) {
        storageHtml = '<span style="color:var(--green-600);font-size:11px;margin-left:4px">📦 ' + esc(it.storage_hint) + '</span>';
      }
      var insufficientHtml = '';
      if (it.state === 'insufficient') {
        insufficientHtml = '<span style="color:var(--amber-600);font-size:11px;margin-left:4px">库存可能不够</span>';
      }
      var actions = '';
      if (it.kind === 'reagent' || it.kind === 'prep') {
        if (it.state === 'ready') {
          actions = '<button class="rc-prep-btn have" data-action="have" data-id="' + esc(it.prep_run_item_id) + '">有</button>';
        } else if (it.state === 'insufficient') {
          actions = '<button class="rc-prep-btn have" data-action="have" data-id="' + esc(it.prep_run_item_id) + '">够用</button>'
            + '<button class="rc-prep-btn missing" data-action="buy" data-id="' + esc(it.prep_run_item_id) + '">不够</button>';
        } else if (it.state === 'prep_now') {
          actions = '<button class="rc-prep-btn have" data-action="have" data-id="' + esc(it.prep_run_item_id) + '">有</button>'
            + '<button class="rc-prep-btn missing" data-action="prep" data-prep-id="' + esc(it.reagent_prep_id) + '" data-id="' + esc(it.prep_run_item_id) + '">去配</button>';
        } else {
          actions = '<button class="rc-prep-btn have" data-action="have" data-id="' + esc(it.prep_run_item_id) + '">有</button>'
            + '<button class="rc-prep-btn missing" data-action="buy" data-id="' + esc(it.prep_run_item_id) + '">缺料</button>';
        }
      } else {
        actions = '<button class="rc-prep-btn have" data-action="have" data-id="' + esc(it.prep_run_item_id) + '">有</button>';
      }
      return '<div class="rc-prep-item' + cls + '" data-id="' + esc(it.prep_run_item_id) + '">'
        + '<span style="flex:0 0 auto">' + icon + '</span>'
        + '<span class="rc-prep-name">' + esc(it.name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">' + esc(kind) + '</span>'
        + '</span>' + qty + mins + tagHtml + storageHtml + insufficientHtml
        + '<span style="flex:0 0 auto;display:flex;gap:4px">' + actions + '</span>'
        + '</div>';
    }).join('');
    var scaleLine = '';
    if (prepBench.scale_unit) {
      var currentScale = prepBench.user_scale || prepBench.default_scale || '未指定';
      scaleLine = '<div style="font-size:12px;color:var(--n-600);padding:6px 15px 8px;border-bottom:1px solid var(--bd-1)">'
        + '计量：<b>' + esc(prepBench.scale_unit) + '</b>'
        + (prepBench.scale_basis ? '<span style="color:var(--n-400)">（' + esc(prepBench.scale_basis) + '）</span>' : '')
        + ' · 当前规模：<b>' + esc(currentScale) + '</b>'
        + ' · <a href="#" id="pb-rescale-link" style="color:var(--blue-600);font-size:11px;cursor:pointer">改规模</a>'
        + '<span id="pb-rescale-input" style="display:none;margin-left:6px">'
        + '<input id="pb-scale-val" type="text" placeholder="如 20个样本" style="font-size:12px;padding:2px 6px;border:1px solid var(--bd-2);border-radius:4px;width:120px">'
        + '<button class="rc-prep-btn have" id="pb-scale-ok" style="margin-left:4px">确认</button>'
        + '<a href="#" id="pb-scale-cancel" style="color:var(--n-400);font-size:11px;margin-left:4px">取消</a>'
        + '</span></div>';
    }
    return '<div class="rc-sec-title">实验准备台</div>'
      + '<div class="rc-prep">'
      + '<div class="rc-prep-h"><span>' + esc(prepBench.protocol_title || '准备台') + '</span>'
      + '<span style="color:var(--n-400);font-size:12px">✅' + (s.ready || 0) + ' 现成 · 🔬' + (s.prep_now || 0) + ' 需配 · 🔶' + (s.insufficient || 0) + ' 待确认 · ⚠️' + (s.missing || 0) + ' 缺料</span></div>'
      + scaleLine
      + rows
      + '<div style="padding:8px 12px;border-top:1px solid var(--bd-1);display:flex;gap:8px;justify-content:flex-end">'
      + '<button class="sh-btn" id="pb-skip">跳过准备</button>'
      + '<button class="sh-btn primary" id="pb-start">开始实验</button>'
      + '</div></div>';
  }

  function scrollCanvasBottom() {
    var canvas = window.shellCanvas && window.shellCanvas();
    if (canvas) {
      canvas.scrollTop = canvas.scrollHeight;
      var inner = canvas.querySelector('#rc');
      if (inner) inner.scrollTop = inner.scrollHeight;
    }
  }

  function scrollToCurrentStep() {
    if (!session || session.mode !== 'protocol') return;
    var canvas = window.shellCanvas && window.shellCanvas();
    if (!canvas) return;
    // 先滚动步骤列表到当前步骤
    var curStep = canvas.querySelector('.rc-step.cur');
    if (curStep) {
      try { curStep.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' }); } catch (_) {}
    }
  }

  // 启动一条"计划"轨道：点击 AI 排程产生的计划实验时，建立 lab_session 并进入实验进行中
  function startPlannedTrack(protocolId, title) {
    if (!protocolId || !window.interactionModeState) return;
    window.interactionModeState.select('protocol', protocolId);
    var ids = window.protocolSessionIdentity ? window.protocolSessionIdentity() : {};
    api('/protocols/session', 'POST', {
      protocol_id: protocolId,
      conversation_id: ids.conversation_id || null,
      lab_session_id: ids.lab_session_id || null,
    }).then(function () {
      if (window.refreshStatus) window.refreshStatus();
      if (window.shellShow) window.shellShow('run');
      if (window.composerRefresh) window.composerRefresh();
      if (window.labStepsReload) window.labStepsReload();
      // 把启动上下文发给聊天
      if (window.composerSend && title) {
        window.composerSend('我现在开始执行方案「' + title + '」，请简要说明第一步怎么做、需要哪些试剂和仪器。');
      }
      reload();
      if (window.chatHomeReload) window.chatHomeReload();
    }).catch(function (e) {
      if (window.alert) window.alert('启动失败：' + (e && e.message ? e.message : e));
    });
  }

  function paint() {
    var canvas = window.shellCanvas && window.shellCanvas();
    if (!canvas || window.shellCurrentView() !== 'run') return;
    if (!session) {
      canvas.classList.add('empty');
      canvas.innerHTML = '加载中…';
      return;
    }
    canvas.classList.remove('empty');
    var ledgerHtml = '';
    if (records && records.items && records.items.length) {
      ledgerHtml = '<div class="rc-sec-title">实验记录</div>'
        + (window.renderLedgerRecords ? window.renderLedgerRecords(records.items) : '')
        + (records.clarifications && records.clarifications.length && window.renderLedgerClarifications
            ? window.renderLedgerClarifications(records.clarifications) : '');
    } else {
      ledgerHtml = '<div class="rc-sec-title">实验记录</div>'
        + '<div style="color:#94a3b8;font-size:13px;padding:18px 0;text-align:center;background:var(--n-00);border:1px dashed var(--bd-2);border-radius:var(--r-lg)">这一页还空着，直接告诉助手你刚做了什么。</div>';
    }
    canvas.innerHTML = '<div id="rc">' + timelineHtml() + stepsHtml() + stepCardHtml() + (prepBenchHtml() || checklistHtml()) + ledgerHtml + '</div>';

    // 绑定时间轴：轨道名点击切换
    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-tl-row-label'), function (label) {
      label.onclick = function (e) {
        if (e.target.closest('[data-archive]')) return; // 归档按钮单独处理
        var protocolId = label.getAttribute('data-tl-protocol');
        var labSessionId = label.getAttribute('data-tl-session');
        var title = label.getAttribute('data-tl-title');
        var isPlanned = label.getAttribute('data-tl-planned') === '1';
        if (!protocolId) return;
        if (isPlanned) {
          startPlannedTrack(protocolId, title);
          return;
        }
        if (!labSessionId) return;
        if (window.switchTrack) {
          window.switchTrack(protocolId, labSessionId, title).then(function () {
            reload();
            if (window.chatHomeReload) window.chatHomeReload();
          });
        }
      };
    });

    // 绑定时间轴：步骤块点击切换 + 跳步
    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-tl-step'), function (blk) {
      blk.onclick = function () {
        var protocolId = blk.getAttribute('data-tl-protocol');
        var labSessionId = blk.getAttribute('data-tl-session');
        var title = blk.getAttribute('data-tl-title');
        var stepNum = parseInt(blk.getAttribute('data-tl-step'), 10);
        var isPlanned = blk.getAttribute('data-tl-planned') === '1';
        if (!protocolId) return;
        if (isPlanned) {
          startPlannedTrack(protocolId, title);
          return;
        }
        if (!labSessionId) return;
        var switchAndJump = function () {
          if (session && session.protocol && session.protocol.id === protocolId) {
            // already on this track → just jump to step
            if (!isNaN(stepNum)) {
              window.moveProtocolStep('jump', stepNum)
                .then(function () { reload(); if (window.chatHomeReload) window.chatHomeReload(); })
                .catch(function (err) { window.alert(err.message); });
            }
          } else if (window.switchTrack) {
            window.switchTrack(protocolId, labSessionId, title).then(function () {
              if (!isNaN(stepNum)) {
                window.moveProtocolStep('jump', stepNum)
                  .then(function () { reload(); if (window.chatHomeReload) window.chatHomeReload(); })
                  .catch(function () {});
              } else {
                reload();
              }
            });
          }
        };
        switchAndJump();
      };
    });

    // 绑定归档按钮
    Array.prototype.forEach.call(canvas.querySelectorAll('[data-archive]'), function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var sessionId = btn.getAttribute('data-archive');
        if (!confirm('确认归档/结束这个实验吗？归档后将从时间轴移除。')) return;
        api('/protocols/archive-track', 'POST', { lab_session_id: sessionId })
          .then(function (res) {
            if (res.ok) {
              reload();
              if (window.chatHomeReload) window.chatHomeReload();
            } else {
              window.alert(res.detail || '归档失败');
            }
          })
          .catch(function () { window.alert('归档失败，请重试。'); });
      };
    });

    // 绑定添加实验按钮
    var addBtn = canvas.querySelector('#rc-tl-add-btn');
    if (addBtn) addBtn.onclick = function () {
      if (window.shellShow) window.shellShow('protocols');
    };

    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-step'), function (node) {
      node.onclick = function () {
        window.moveProtocolStep('jump', parseInt(node.dataset.n, 10))
          .then(function (result) { reload(); if (window.chatHomeReload) window.chatHomeReload(); return result; })
          .catch(function (error) { window.alert(error.message); });
      };
    });
    var edit = document.getElementById('rc-edit');
    if (edit) edit.onclick = function () { if (window.openProtocolEditor) window.openProtocolEditor(); };
    var prev = document.getElementById('rc-prev'), next = document.getElementById('rc-next');
    if (prev) prev.onclick = function () { window.moveProtocolStep('prev').then(function (result) { reload(); if (window.chatHomeReload) window.chatHomeReload(); return result; }).catch(function (error) { window.alert(error.message); }); };
    if (next) next.onclick = function () { window.moveProtocolStep('next').then(function (result) { reload(); if (window.chatHomeReload) window.chatHomeReload(); return result; }).catch(function (error) { window.alert(error.message); }); };
    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-prep-item'), function (row) {
      var key = row.getAttribute('data-key');
      var haveBtn = row.querySelector('[data-action="have"]');
      var missingBtn = row.querySelector('[data-action="missing"]');
      if (haveBtn) haveBtn.onclick = function (e) {
        e.stopPropagation();
        checklistState[key] = 'have';
        saveChecklistState();
        paint();
        scrollCanvasBottom();
      };
      if (missingBtn) missingBtn.onclick = function (e) {
        e.stopPropagation();
        checklistState[key] = 'missing';
        saveChecklistState();
        var item = checklistItems().filter(function (x) { return x.key === key; })[0];
        if (item && item.prep && item.prep.reagent_prep_id) {
          window.prepStartFlow?.(item.prep.reagent_prep_id);
        } else if (item && item.prep && item.prep.name && window.prepStartFlow) {
          // 如果清单里带的是试剂配置库条目，直接进入对应配制流程
          var match = findPrepForName(item.prep.name || item.name);
          if (match && match.reagent_prep_id) window.prepStartFlow(match.reagent_prep_id);
        } else {
          paint();
          scrollCanvasBottom();
          if (window.alert) window.alert('没有找到可直接配制的配方，可以告诉小科“创建这个试剂配方”');
        }
      };
    });

    // 准备台按钮绑定（优先于旧清单）
    Array.prototype.forEach.call(canvas.querySelectorAll('.rc-prep-item[data-id]'), function (row) {
      var itemId = row.getAttribute('data-id');
      var haveBtn = row.querySelector('button[data-action="have"]');
      var prepBtn = row.querySelector('button[data-action="prep"]');
      var buyBtn = row.querySelector('button[data-action="buy"]');
      if (haveBtn) haveBtn.onclick = function (e) {
        e.stopPropagation();
        api('/prep-bench/items/' + encodeURIComponent(itemId), 'PATCH', { manual_state: 'have' })
          .then(function () { reload(); });
      };
      if (prepBtn) prepBtn.onclick = function (e) {
        e.stopPropagation();
        api('/prep-bench/items/' + encodeURIComponent(itemId), 'PATCH', { manual_state: 'have' })
          .then(function () {
            var prepId = prepBtn.getAttribute('data-prep-id');
            if (prepId && window.prepStartFlow) window.prepStartFlow(prepId);
          });
      };
      if (buyBtn) buyBtn.onclick = function (e) {
        e.stopPropagation();
        api('/prep-bench/items/' + encodeURIComponent(itemId), 'PATCH', { manual_state: 'missing' })
          .then(function () { reload(); });
      };
    });
    var pbStart = document.getElementById('pb-start');
    if (pbStart) pbStart.onclick = function () {
      api('/prep-bench/status', 'POST', { status: 'ready' }).then(function () { reload(); });
    };
    var pbSkip = document.getElementById('pb-skip');
    if (pbSkip) pbSkip.onclick = function () {
      api('/prep-bench/status', 'POST', { status: 'skipped' }).then(function () { reload(); });
    };

    // 缩放输入
    var rescaleLink = document.getElementById('pb-rescale-link');
    var rescaleInput = document.getElementById('pb-rescale-input');
    if (rescaleLink) rescaleLink.onclick = function (e) {
      e.preventDefault();
      rescaleLink.style.display = 'none';
      if (rescaleInput) rescaleInput.style.display = 'inline';
      var inp = document.getElementById('pb-scale-val');
      if (inp) inp.focus();
    };
    var scaleCancel = document.getElementById('pb-scale-cancel');
    if (scaleCancel) scaleCancel.onclick = function (e) {
      e.preventDefault();
      if (rescaleInput) rescaleInput.style.display = 'none';
      if (rescaleLink) rescaleLink.style.display = 'inline';
    };
    var scaleOk = document.getElementById('pb-scale-ok');
    if (scaleOk) scaleOk.onclick = function () {
      var val = (document.getElementById('pb-scale-val') || {}).value || '';
      if (!val.trim()) return;
      scaleOk.textContent = '计算中…';
      scaleOk.disabled = true;
      api('/prep-bench/scale', 'PATCH', { user_scale: val.trim() }).then(function () {
        reload();
      }).catch(function () {
        scaleOk.textContent = '确认';
        scaleOk.disabled = false;
      });
    };

    scrollCanvasBottom();
  }

  function reload() {
    var path = window.protocolSessionUrl
      ? window.protocolSessionUrl('/protocols/session/steps')
      : '/protocols/session/steps';
    var recordPath = window.protocolSessionUrl
      ? window.protocolSessionUrl('/record/history')
      : '/record/history';
    return api(path).then(function (s) {
      session = s;
      var prepPath = '/reagent-prep';
      var checklistPath = session && session.protocol && session.protocol.id
        ? '/checklists/' + encodeURIComponent(session.protocol.id)
        : '';
      return Promise.all([
        api(recordPath).catch(function () { return null; }),
        api(prepPath).catch(function () { return {items: []}; }),
        checklistPath ? api(checklistPath).catch(function () { return null; }) : Promise.resolve(null),
        api('/protocols/active-tracks').catch(function () { return {tracks: []}; }),
        api('/prep-bench').catch(function () { return null; }),
      ]);
    }).then(function (out) {
      records = out[0];
      reagentPrepList = (out[1] && out[1].items) || [];
      checklist = out[2];
      activeTracks = (out[3] && out[3].tracks) || [];
      prepBench = out[4];
      paint();
      // 自动滚动到当前步骤卡片
      scrollToCurrentStep();
      return session;
    }).catch(function () {});
  }

  window.runCanvasRender = function () { paint(); reload(); };
  window.runReload = reload;

  // 工具结果作为第一公民：聊天流解析出的工具卡片会通过 tool_cards.js 转发到这里。
  // 画布用与聊天同一份 renderArtifact 渲染，不再按工具名写特例。
  window.runPushTool = function (view) {
    var canvas = window.shellCanvas && window.shellCanvas();
    if (!canvas || window.shellCurrentView() !== 'run') return;
    if (!window.renderArtifact) return;
    var artifact = (view && view.artifact) || view || {};
    if (!artifact || artifact.type === 'action') return; // 纯跳转动作不必在画布重复画
    var slot = canvas.querySelector('#rc-tool-artifacts');
    if (!slot) {
      slot = document.createElement('div');
      slot.id = 'rc-tool-artifacts';
      var inner = canvas.querySelector('#rc');
      if (inner) inner.appendChild(slot); else canvas.appendChild(slot);
    }
    var wrap = document.createElement('div');
    wrap.className = 'rc-tool-artifact';
    wrap.innerHTML = window.renderArtifact(artifact);
    slot.appendChild(wrap);
    scrollCanvasBottom();
  };

  document.addEventListener('lab:experiment-changed', function () {
    if (window.shellCurrentView && window.shellCurrentView() === 'run') {
      reload();
    } else if (window.shellShow) {
      // 如果不在实验视图，切换到实验视图并刷新（步骤变了应该让用户看到）
      window.shellShow('run');
      reload();
    }
  });

  // 轨道切换：用户点了另一个实验轨道，重新加载画布
  document.addEventListener('lab:track-switched', function () {
    reload();
  });

  // SSE 推送的新记录到了：如果在实验视图，高亮最新条目让用户看到。
  document.addEventListener('lab:record-arrived', function () {
    if (window.shellCurrentView && window.shellCurrentView() === 'run') {
      reload().then(function () {
        // reload 完成后找到最后一条记录并高亮闪一下。
        var canvas = window.shellCanvas && window.shellCanvas();
        if (!canvas) return;
        var records = canvas.querySelectorAll('.nb-entry, .ledger-record');
        if (records.length) {
          var last = records[records.length - 1];
          last.scrollIntoView({ behavior: 'smooth', block: 'center' });
          last.classList.add('nb-flash');
          setTimeout(function () { last.classList.remove('nb-flash'); }, 2500);
        }
      });
    }
  });

  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);
  document.addEventListener('shell-ready', function () {
    reload();
    setInterval(function () { if (window.shellCurrentView() === 'run') reload(); }, 3000);
  });
})();
