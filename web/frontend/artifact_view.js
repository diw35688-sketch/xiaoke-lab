// 统一 Artifact 渲染器：聊天、实验画布、记录本共用同一份渲染逻辑。
//
// 工具结果是第一公民：后端给每张工具卡片附带 artifact 合同
//   { version, type, tool, title, status, summary, lines, actions, data }
// 前端只按 type 画，不按工具名写特例。
//
// 暴露：
//   window.renderArtifact(artifact, {interactive}) -> HTML 字符串
//   window.artifactFirstLine(artifact) -> 用于一句话正文确认
(() => {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function asLines(artifact) {
    const lines = Array.isArray(artifact && artifact.lines) ? artifact.lines : [];
    return lines.map(function (x) { return String(x == null ? '' : x); }).filter(Boolean);
  }

  function checklistRowsHtml(data) {
    // 复用实验画布已有的 .rc-prep* 样式，保证聊天与画布观感一致。
    const rows = [];
    const reagents = (data && data.reagents) || [];
    reagents.forEach(function (r) {
      const name = r.name || '';
      const have = !!r.found_in_storage;
      rows.push('<div class="rc-prep-item' + (have ? ' have' : '') + '">'
        + '<span style="flex:0 0 auto">' + (have ? '✅' : '☐') + '</span>'
        + '<span class="rc-prep-name">' + esc(name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">试剂</span></span>'
        + '</div>');
    });
    (((data && data.equipment) || []) || []).forEach(function (name) {
      rows.push('<div class="rc-prep-item"><span style="flex:0 0 auto">☐</span>'
        + '<span class="rc-prep-name">' + esc(name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">仪器</span></span></div>');
    });
    (((data && data.consumables) || []) || []).forEach(function (name) {
      rows.push('<div class="rc-prep-item"><span style="flex:0 0 auto">☐</span>'
        + '<span class="rc-prep-name">' + esc(name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">耗材</span></span></div>');
    });
    (((data && data.prep_requirements) || []) || []).forEach(function (p) {
      const name = p.name_zh || p.name || '';
      rows.push('<div class="rc-prep-item"><span style="flex:0 0 auto">☐</span>'
        + '<span class="rc-prep-name">' + esc(name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">需配制</span></span></div>');
    });
    return rows.join('');
  }

  // ── 准备台渲染（artifact.type === 'prep_bench'）──
  var _SENSITIVITY_LABEL = {
    prechill: '需预冷', overnight: '需过夜', fresh: '现配现用', normal: '',
  };

  function prepBenchHtml(data) {
    if (!data || data.message) return '';
    var s = data.summary || {};
    var rows = (data.items || []).map(function (it) {
      var mark = { ready: '✅', prep_now: '🔬', missing: '⚠️', insufficient: '🔶' }[it.state] || '☐';
      var qty = it.quantity ? ' <span style="color:var(--n-600)">' + esc(it.quantity) + '</span>' : '';
      var tag = _SENSITIVITY_LABEL[it.time_sensitivity] || '';
      var tagColor = it.time_sensitivity === 'overnight' ? 'var(--red-100),var(--red-600)'
        : it.time_sensitivity === 'prechill' ? 'var(--blue-100),var(--blue-600)'
        : it.time_sensitivity === 'fresh' ? 'var(--amber-100),var(--amber-600)' : '';
      var tagHtml = tag && tagColor ? ' <span style="background:' + tagColor.split(',')[0] + ';color:' + tagColor.split(',')[1] + ';font-size:10px;padding:1px 5px;border-radius:4px">' + esc(tag) + '</span>' : '';
      var mins = it.estimated_minutes ? ' <span style="color:var(--n-500);font-size:11px">约' + it.estimated_minutes + '分钟</span>' : '';
      var kind = { reagent: '试剂', equipment: '仪器', consumable: '耗材', prep: '需配制' }[it.kind] || '';
      var cls = it.state === 'ready' ? ' have' : (it.state === 'insufficient' ? ' insuf' : '');
      var storageHtml = it.storage_hint ? ' <span style="color:var(--green-600);font-size:11px">📦 ' + esc(it.storage_hint) + '</span>' : '';
      var insufHtml = it.state === 'insufficient' ? ' <span style="color:var(--amber-600);font-size:11px">库存可能不够</span>' : '';
      return '<div class="rc-prep-item' + cls + '">'
        + '<span style="flex:0 0 auto">' + mark + '</span>'
        + '<span class="rc-prep-name">' + esc(it.name)
        + '<span style="color:var(--n-400);font-size:11px;margin-left:6px">' + esc(kind) + '</span>'
        + '</span>' + qty + mins + tagHtml + storageHtml + insufHtml + '</div>';
    }).join('');
    var scaleHtml = '';
    if (data.scale_unit) {
      var curScale = data.user_scale || data.default_scale || '未指定';
      scaleHtml = '<div style="font-size:12px;color:var(--n-600);padding:6px 15px 8px;border-bottom:1px solid var(--bd-1)">'
        + '计量方式：<b>' + esc(data.scale_unit) + '</b>'
        + (data.scale_basis ? '（' + esc(data.scale_basis) + '）' : '')
        + ' · 当前规模：<b>' + esc(curScale) + '</b></div>';
    }
    return '<div class="rc-prep">'
      + '<div class="rc-prep-h"><span>' + esc(data.protocol_title || '实验准备台') + '</span>'
      + '<span style="color:var(--n-400);font-size:12px">✅' + (s.ready || 0) + ' · 🔬' + (s.prep_now || 0) + ' · 🔶' + (s.insufficient || 0) + ' · ⚠️' + (s.missing || 0) + '</span></div>'
      + scaleHtml
      + (rows || '<div class="rc-prep-item">当前没有准备项。</div>')
      + '</div>';
  }

  window.renderArtifact = function (artifact, opts) {
    opts = opts || {};
    if (!artifact || typeof artifact !== 'object') return '';
    const type = artifact.type || 'result';
    const title = artifact.title || '';
    const status = artifact.status || 'done';
    const data = artifact.data;
    let body = '';

    if (type === 'checklist' && data && !data.message) {
      const rows = checklistRowsHtml(data);
      body = '<div class="rc-prep"><div class="rc-prep-h"><span>' + esc(title || '实验前准备清单')
        + '</span><span style="color:var(--n-400);font-size:12px">逐项确认</span></div>'
        + (rows || '<div class="rc-prep-item">当前没有可用的准备材料清单。</div>')
        + '</div>';
    } else if (type === 'prep_bench' && data && !data.message) {
      body = prepBenchHtml(data);
    } else {
      const lines = asLines(artifact);
      body = '<div class="artifact-lines">' + lines.map(function (l) {
        return '<div>' + esc(l) + '</div>';
      }).join('') + '</div>';
    }
    return '<div class="artifact artifact-' + esc(type) + '">'
      + '<div class="artifact-head"><span class="artifact-ic">⚙</span>'
      + '<span class="artifact-title">' + esc(title) + '</span>'
      + '<span class="artifact-status st ' + esc(status) + '">' + esc(status) + '</span></div>'
      + body + '</div>';
  };

  window.artifactFirstLine = function (artifact) {
    const lines = asLines(artifact);
    return lines.length ? lines[0] : (artifact && artifact.title ? artifact.title : '');
  };
})();
