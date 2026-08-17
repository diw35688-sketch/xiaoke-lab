"""呈现泵：唯一拥有 stdout 写入权的执行流。

后台业务线程只把 Intent 投递给 PresentationCoordinator，本泵从 Coordinator
取货、交给 Renderer 渲染、再写入输出。Renderer 以协议约定（只要会
`render(intent) -> str` 就算满足），pump 不绑定 TerminalRenderer 具体类。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol

from src.core.presentation_coordinator import PresentationCoordinator
from src.core.presentation_intent import PresentationIntent


class Renderer(Protocol):
    """pump 依赖的渲染契约；TerminalRenderer 与未来 Web/TTS 渲染器都满足它。"""

    def render(self, intent: PresentationIntent) -> str: ...


@dataclass(frozen=True)
class PresentationDeliveryFailure:
    """一条呈现意图的交付失败摘要。"""

    intent_id: str
    error_type: str
    reason: str


class PresentationDeliveryError(RuntimeError):
    """flush 发现 Renderer/output 交付失败。"""

    def __init__(
        self,
        failures: tuple[PresentationDeliveryFailure, ...],
    ) -> None:
        self.failures = failures
        super().__init__(f"呈现交付失败 {len(failures)} 条。")


class PresentationPump:
    """循环取货 → 渲染 → 输出的消费者线程；唯一写 stdout 的地方。"""

    def __init__(
        self,
        coordinator: PresentationCoordinator,
        renderer: Renderer,
        output: Callable[[str], None] = print,
        event_tone_player: (
            Callable[[PresentationIntent], None] | None
        ) = None,
    ) -> None:
        self._coordinator = coordinator
        self._renderer = renderer
        self._output = output
        self._event_tone_player = event_tone_player
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure_lock = threading.Lock()
        self._failures: list[PresentationDeliveryFailure] = []

    def start(self) -> None:
        """启动泵线程（守护线程，不阻塞主进程退出）。"""

        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="presentation-pump",
        )
        self._thread.start()

    def flush(self, timeout: float | None = None) -> bool:
        """等待调用前已投递的消息全部完成交付。

        返回 True 表示 pending 和 in-flight 均归零；超时返回 False。
        Renderer/output 若失败，在全部已取走消息完成尝试后抛出
        PresentationDeliveryError。
        """

        if not self._coordinator.join(timeout):
            return False
        with self._failure_lock:
            if self._failures:
                raise PresentationDeliveryError(tuple(self._failures))
        return True

    def stop(self, timeout: float | None = None) -> None:
        """请求停止并等待线程退出。调用方需先用 flush 确认交付。"""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            intents = self._coordinator.drain(timeout=0.1)
            if not intents:
                continue
            for intent in intents:
                try:
                    self._output(self._renderer.render(intent))
                    if self._event_tone_player is not None:
                        self._event_tone_player(intent)
                except Exception as error:
                    with self._failure_lock:
                        self._failures.append(PresentationDeliveryFailure(
                            intent_id=intent.intent_id,
                            error_type=type(error).__name__,
                            reason=str(error),
                        ))
                finally:
                    self._coordinator.mark_completed()
