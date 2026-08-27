// Finalize the temporary assistant bubble after a committed Turn arrives.
(() => {
  function messageRow(reply) {
    return reply && reply.parentElement
      && reply.parentElement.classList
      && reply.parentElement.classList.contains('message')
      ? reply.parentElement
      : reply;
  }

  function settleTurnReplySurface({reply, assistant, publishAnswer}) {
    if (assistant?.payload?.presentation === 'clarification_card') {
      const row = messageRow(reply);
      row?.remove?.();
      return 'card';
    }
    publishAnswer(assistant?.payload?.text || '处理完成。');
    return 'text';
  }

  window.settleTurnReplySurface = settleTurnReplySurface;
})();
