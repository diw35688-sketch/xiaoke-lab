/* 个人中心：左侧个人导航 + 右侧分区设置页。 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var AVATAR_STYLES = [
    ['avataaars', 'Avataaars 卡通人物'],
    ['adventurer', 'Adventurer 冒险家'],
    ['big-ears', 'Big Ears 大耳朵'],
    ['big-smile', 'Big Smile 大笑脸'],
    ['bottts', 'Bottts 机器人'],
    ['croodles', 'Croodles 涂鸦'],
    ['dylan', 'Dylan 简笔'],
    ['fun-emoji', 'Fun Emoji 表情'],
    ['icons', 'Icons 图标'],
    ['identicon', 'Identicon 几何'],
    ['lorelei', 'Lorelei 女孩'],
    ['micah', 'Micah 插画'],
    ['miniavs', 'Miniavs 迷你'],
    ['notionists', 'Notionists 人物'],
    ['open-peeps', 'Open Peeps 线条'],
    ['personas', 'Personas 人物'],
    ['pixel-art', 'Pixel Art 像素'],
    ['rings', 'Rings 圆环'],
    ['shapes', 'Shapes 形状'],
    ['thumbs', 'Thumbs 拇指']
  ];

  function avatarUrl(seed, style, size) {
    style = style || 'avataaars';
    return 'https://api.dicebear.com/9.x/' + encodeURIComponent(style) + '/svg?seed=' + encodeURIComponent(seed || 'user') + '&size=' + (size || 128);
  }

  function savedAvatarStyle() {
    try { return localStorage.getItem('lab-user-avatar-style') || 'avataaars'; } catch (_) { return 'avataaars'; }
  }

  window.dicebearAvatarUrl = avatarUrl;
  window.applyUserAvatarStyle = function (style) {
    var avatarEl = document.getElementById('wb-user-avatar');
    if (!avatarEl) return;
    try { localStorage.setItem('lab-user-avatar-style', style || 'avataaars'); } catch (_) {}
    if (window.__userSeed) {
      avatarEl.innerHTML = '<img src="' + avatarUrl(window.__userSeed, style || savedAvatarStyle(), 28) + '" alt="" style="width:28px;height:28px;border-radius:50%;display:block;object-fit:cover">';
    } else {
      avatarEl.textContent = '小';
    }
  };

  function api(path, method, body) {
    var opts = { method: method || 'GET' };
    if (body) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) { return r.json(); });
  }

  function statTile(value, label) {
    return '<div style="flex:1;background:#f8fafc;border:1px solid #eef2f7;border-radius:14px;padding:18px 10px;text-align:center">'
      + '<div style="font-size:26px;font-weight:700;color:#0f172a">' + value + '</div>'
      + '<div style="color:#64748b;font-size:12px;margin-top:5px">' + label + '</div></div>';
  }

  function menuItem(id, label) {
    return '<button type="button" class="pc-menu-item" data-pc-target="' + id + '" style="display:flex;align-items:center;gap:9px;padding:10px 12px;border:0;background:transparent;border-radius:10px;font-size:13px;color:#475569;cursor:pointer;text-align:left;width:100%">'
      + '<span style="width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.6"></span>' + label
      + '</button>';
  }

  function renderPersonalCenter(canvas) {
    Promise.all([
      api('/auth/state'),
      api('/auth/sessions'),
      api('/settings'),
      api('/storage/stats'),
      api('/agent/timeline')
    ]).then(function (out) {
      var s = out[0], sessions = out[1], settings = out[2], storage = out[3], timeline = out[4];
      if (!s.authenticated) {
        canvas.innerHTML = '<div style="max-width:560px;margin:8vh auto 0;text-align:center;color:#64748b">'
          + '<div style="font-size:18px;font-weight:600;color:#0f172a;margin-bottom:10px">未登录</div>'
          + '<p>请先登录，才能进入个人中心。</p>'
          + '<button class="sh-btn primary" id="personal-go-login">去登录</button></div>';
        canvas.querySelector('#personal-go-login').onclick = function () { location.href = '/login'; };
        return;
      }
      var u = s.user || {};
      var profile = (settings.settings && settings.settings.owner_profile) || {};
      var sessionsItems = (sessions && sessions.items) || [];
      var storageStats = storage || {};
      var timelineSummary = (timeline && timeline.summary) || {};
      var skin = 'paper'; try { skin = localStorage.getItem('lab-skin') || 'paper'; } catch (_) {}
      var onPaper = skin === 'paper';
      var displayName = u.display_name || u.username || '';
      var profileLines = [];
      if (profile.field) profileLines.push('<div style="margin-bottom:6px"><span style="color:#94a3b8;font-size:12px">研究领域</span><div style="color:#0f172a;font-size:14px;margin-top:2px">' + esc(profile.field) + '</div></div>');
      if (profile.methods) profileLines.push('<div style="margin-bottom:6px"><span style="color:#94a3b8;font-size:12px">常用方法</span><div style="color:#0f172a;font-size:14px;margin-top:2px">' + esc(profile.methods) + '</div></div>');
      if (profile.notes) profileLines.push('<div><span style="color:#94a3b8;font-size:12px">偏好备注</span><div style="color:#0f172a;font-size:14px;margin-top:2px">' + esc(profile.notes) + '</div></div>');
      if (!profileLines.length) profileLines.push('<div style="color:#94a3b8;font-size:13px">还没填写主人画像。填写后，每日规划会更了解你的实验习惯。</div>');

      var avatarStyle = savedAvatarStyle();
      var sections = [
        ['account', '账号信息', '<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">'
          + '<img id="personal-avatar-img" src="' + avatarUrl(u.username || 'user', avatarStyle, 128) + '" alt="头像" style="width:64px;height:64px;border-radius:20px;background:#f1f5f9;object-fit:cover">'
          + '<div><div style="font-size:22px;font-weight:700;color:#0f172a">' + esc(u.username || '') + '</div>'
          + '<div style="color:#64748b;font-size:13px;margin-top:3px">' + (u.is_admin ? '管理员' : '普通用户') + (displayName && displayName !== u.username ? ' · ' + esc(displayName) : '') + '</div></div></div>'
          + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap">'
          + '<span style="font-size:12px;color:#475569">头像风格：<b id="personal-avatar-style-name">' + esc(avatarStyle) + '</b></span>'
          + '<button class="sh-btn" id="personal-avatar-random" type="button">🎲 随机换一个</button>'
          + '</div>'
          + '<label style="display:block;margin-bottom:12px"><span style="font-size:12px;color:#475569;display:block;margin-bottom:4px">昵称 / 显示名</span>'
          + '<input id="personal-display-name" type="text" value="' + esc(displayName) + '" maxlength="64" placeholder="例如：张三、小科、导师" style="width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #cbd5e1;border-radius:8px;font-size:14px;font-family:inherit"></label>'
          + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">'
          + '<button class="sh-btn primary" id="personal-save-name" type="button">保存昵称</button>'
          + '<span id="personal-name-msg" style="font-size:12px;color:#64748b"></span></div>'
          + '<div style="display:flex;gap:8px;flex-wrap:wrap">'
          + '<button class="sh-btn primary" id="personal-logout">退出登录</button>'
          + '<button class="sh-btn" id="personal-all">退出所有设备</button>'
          + '</div>'],
        ['stats', '数据统计', '<div style="display:flex;gap:10px;flex-wrap:wrap">'
          + statTile(timelineSummary.record_count || 0, '今日实验记录')
          + statTile(storageStats.total || 0, '储存物品')
          + statTile(sessionsItems.length, '登录设备')
          + '</div>'
          + '<div style="margin-top:12px;color:#94a3b8;font-size:12px">可以在“今日规划”里查看完整时间线。</div>'],
        ['appearance', '外观', '<div style="display:flex;gap:8px;flex-wrap:wrap">'
          + '<button class="sh-btn' + (onPaper ? ' primary' : '') + '" id="personal-skin-paper">纸面外观</button>'
          + '<button class="sh-btn' + (!onPaper ? ' primary' : '') + '" id="personal-skin-classic">经典外观</button>'
          + '</div>'],
        ['profile', '个性化', '<div style="color:#64748b;font-size:13px;line-height:1.8;margin-bottom:12px">' + profileLines.join('') + '</div>'
          + '<button class="sh-btn" id="personal-edit-profile">编辑主人画像</button>'],
        ['security', '安全', '<label style="display:block;margin-bottom:12px"><span style="font-size:12px;color:#475569;display:block;margin-bottom:4px">当前密码</span>'
          + '<input type="password" id="personal-old" style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px"></label>'
          + '<label style="display:block;margin-bottom:12px"><span style="font-size:12px;color:#475569;display:block;margin-bottom:4px">新密码</span>'
          + '<input type="password" id="personal-new" style="width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px"></label>'
          + '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><button class="sh-btn primary" id="personal-change-pw">保存新密码</button>'
          + '<span id="personal-pw-msg" style="font-size:12px;color:#64748b"></span></div>'
          + '<div style="margin-top:14px;padding-top:12px;border-top:1px solid #eef2f7;color:#64748b;font-size:12px">登录设备：' + sessionsItems.length + ' 个</div>'],
        ['links', '快捷入口', '<div style="display:flex;gap:8px;flex-wrap:wrap">'
          + '<button class="sh-btn" id="personal-go-agent">今日规划</button>'
          + '<button class="sh-btn" id="personal-go-community">社区</button>'
          + '</div>']
      ];

      var body = sections.map(function (sec) {
        return '<section id="pc-' + sec[0] + '" class="pc-section" style="background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:22px 24px;margin-bottom:14px">'
          + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:14px">' + sec[1] + '</div>'
          + sec[2]
          + '</section>';
      }).join('');

      canvas.innerHTML = '<div style="max-width:860px;margin:0 auto">' + body + '</div>';

      canvas.querySelector('#personal-logout').onclick = function () {
        api('/auth/logout', 'POST').then(function () { location.href = '/login'; });
      };
      canvas.querySelector('#personal-all').onclick = function () {
        if (!confirm('确定退出所有设备登录？')) return;
        api('/auth/logout-all', 'POST').then(function () { location.href = '/login'; });
      };
      var openSettingsBtn = canvas.querySelector('#personal-open-settings');
      if (openSettingsBtn) openSettingsBtn.onclick = function () { window.shellShow('settings'); };
      var saveNameBtn = canvas.querySelector('#personal-save-name');
      if (saveNameBtn) {
        saveNameBtn.onclick = function () {
          var input = canvas.querySelector('#personal-display-name');
          var msg = canvas.querySelector('#personal-name-msg');
          var name = (input && input.value || '').trim();
          saveNameBtn.disabled = true;
          if (msg) { msg.textContent = '保存中…'; msg.style.color = '#64748b'; }
          fetch('/auth/profile', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name })
          }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
            .then(function (res) {
              saveNameBtn.disabled = false;
              if (!res.ok) {
                if (msg) { msg.textContent = res.d.detail || '保存失败'; msg.style.color = '#dc2626'; }
                return;
              }
              var updatedName = res.d.user && (res.d.user.display_name || res.d.user.username) || name || '用户';
              if (msg) { msg.textContent = '✅ 昵称已更新'; msg.style.color = '#047857'; }
              var sidebarName = document.getElementById('wb-user-name');
              if (sidebarName) sidebarName.textContent = updatedName;
              setTimeout(function () { if (msg) msg.textContent = ''; }, 2000);
            })
            .catch(function (e) {
              saveNameBtn.disabled = false;
              if (msg) { msg.textContent = '保存失败：' + String(e); msg.style.color = '#dc2626'; }
            });
        };
      }
      var avatarStyleNameEl = canvas.querySelector('#personal-avatar-style-name');
      var avatarRandomBtn = canvas.querySelector('#personal-avatar-random');
      if (avatarRandomBtn) {
        avatarRandomBtn.onclick = function () {
          var pick = AVATAR_STYLES[Math.floor(Math.random() * AVATAR_STYLES.length)];
          var style = pick[0];
          try { localStorage.setItem('lab-user-avatar-style', style); } catch (_) {}
          if (avatarStyleNameEl) avatarStyleNameEl.textContent = pick[1];
          var img = canvas.querySelector('#personal-avatar-img');
          if (img) img.src = avatarUrl(u.username || 'user', style, 128);
          if (typeof window.applyUserAvatarStyle === 'function') window.applyUserAvatarStyle(style);
        };
      }
      canvas.querySelector('#personal-edit-profile').onclick = function () { window.shellShow('settings'); };
      canvas.querySelector('#personal-go-agent').onclick = function () { window.shellShow('agent'); };
      canvas.querySelector('#personal-go-community').onclick = function () { window.shellShow('community'); };
      var goSettingsBtn = canvas.querySelector('#personal-go-settings');
      if (goSettingsBtn) goSettingsBtn.onclick = function () { window.shellShow('settings'); };
      canvas.querySelector('#personal-skin-paper').onclick = function () {
        try { localStorage.setItem('lab-skin', 'paper'); } catch (_) {}
        location.reload();
      };
      canvas.querySelector('#personal-skin-classic').onclick = function () {
        try { localStorage.setItem('lab-skin', 'classic'); } catch (_) {}
        location.reload();
      };
      canvas.querySelector('#personal-change-pw').onclick = function () {
        var old = canvas.querySelector('#personal-old').value;
        var neu = canvas.querySelector('#personal-new').value;
        api('/auth/password', 'POST', { current_password: old, new_password: neu }).then(function (d) {
          var msg = canvas.querySelector('#personal-pw-msg');
          if (d && d.detail) { msg.textContent = d.detail; msg.style.color = '#dc2626'; return; }
          msg.textContent = '密码已修改'; msg.style.color = '#047857';
          canvas.querySelector('#personal-old').value = '';
          canvas.querySelector('#personal-new').value = '';
        });
      };
    }).catch(function () {
      canvas.innerHTML = '<div style="color:#94a3b8;font-size:13px;padding:40px;text-align:center">加载失败</div>';
    });
  }
  window.shellRegisterView('personal', renderPersonalCenter);
  window.renderPersonalCenter = renderPersonalCenter;
})();
