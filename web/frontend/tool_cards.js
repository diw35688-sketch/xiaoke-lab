// 工具卡片转发：卡片渲染已迁到中间工作画布（run_canvas.js）。
// 这里只保留一个薄转发，保证聊天流解析出的卡片事件仍能落到画布上。
(function () {
  window.labToolCard = function (view) {
    if (window.runPushTool) window.runPushTool(view);
  };
})();
