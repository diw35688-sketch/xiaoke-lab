/* 浏览器自动填充守卫：防止邮箱/历史搜索词被塞进搜索框。
 * 覆盖所有 type=search 以及 placeholder 含“搜索”的文本框。
 * 策略：autocomplete=off + 随机 name + 聚焦/输入时清掉邮箱样式的自动填充值。
 */
(function () {
  function looksLikeEmail(value) {
    return /\S+@\S+/.test(value || '');
  }

  function guard(input) {
    if (!input || input.getAttribute('data-autofill-guard')) return;
    input.setAttribute('data-autofill-guard', '1');
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.setAttribute('spellcheck', 'false');
    if (!input.name || input.name.indexOf('noname-') !== 0) {
      input.name = 'noname-' + Math.random().toString(36).slice(2, 10);
    }
    input.addEventListener('focus', function () {
      if (looksLikeEmail(input.value)) input.value = '';
    });
    input.addEventListener('input', function () {
      if (looksLikeEmail(input.value)) input.value = '';
    });
    // 浏览器可能在页面加载后/失去焦点时再次写入自动填充值，
    // 轮询兜底时发现邮箱样式的值立即清空，不只是等下一次聚焦。
    if (looksLikeEmail(input.value)) input.value = '';
  }

  function scan() {
    document.querySelectorAll('input[type="search"], input[type="text"][placeholder*="搜索"]').forEach(function (el) {
      guard(el);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scan);
  } else {
    scan();
  }
  // 页面是动态渲染的，轮询兜底；开销极小。
  setInterval(scan, 1000);
})();
