// Web 唤醒词判定：只负责规范化 ASR 文本并判断是否命中。
// 麦克风、VAD、ASR 和连续通话生命周期仍由 phone_call.js 统一编排。
(function (root) {
  const CANONICAL_WAKE_WORD = '小科小科';
  // SenseVoice 对“科”的常见同音转写。列表保持封闭，避免把普通实验口述
  // 通过宽泛的编辑距离误判为唤醒词。
  const DEFAULT_WAKE_WORDS = [
    '小科小科', '小柯小柯', '小可小可', '小颗小颗',
    '晓科晓科', '晓柯晓柯', '晓可晓可',
    '你好小科', '你好小柯', '你好小可',
    // ASR 偶尔会把紧邻的重复词合并；只接受整段短句为单个称呼。
    '小科', '小柯', '小可',
  ];

  function normalizeWakeText(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/[\s，。！？、,.!?；;：:'"“”‘’（）()\[\]【】_-]+/g, '');
  }

  function detectWakeWord(text, wakeWords) {
    const normalized = normalizeWakeText(text);
    const candidates = Array.isArray(wakeWords) && wakeWords.length
      ? wakeWords : DEFAULT_WAKE_WORDS;
    for (const wakeWord of candidates) {
      const expected = normalizeWakeText(wakeWord);
      if (!expected) continue;
      // 单个“小科/小柯/小可”只允许整段完全匹配；较长唤醒词可以出现在
      // “小科小科请开始”等短句中。
      const matched = expected.length <= 2
        ? normalized === expected
        : normalized.includes(expected);
      if (matched) return CANONICAL_WAKE_WORD;
    }
    return null;
  }

  root.XiaokeWakeWord = {
    CANONICAL_WAKE_WORD,
    DEFAULT_WAKE_WORDS,
    normalizeWakeText,
    detectWakeWord,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.XiaokeWakeWord;
  }
})(typeof window !== 'undefined' ? window : globalThis);
