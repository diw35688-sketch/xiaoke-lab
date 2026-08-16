"""为可打断播报提供无锁的代数取消范围。"""


class CancelScope:
    """用代数判断一次播报是否已经过时。

    线程安全前提是：只有一个写者（触发打断或开启新播报的线程），
    可以有多个读者（播报线程）。在这个前提下，依赖CPython GIL对整数
    读写的原子性，因此不需要锁；如果将来出现多个写者，必须重新评估
    这里的并发模型，不能把当前实现当成通用的多写者同步原语。

    本轮只实现代数取消，不照抄异步发送循环所需的``discarding``或
    ``_discarded_generation``。那是给异步发送循环丢弃过时输出用的，
    本轮有意不实现，待真实播放接入时再评估。
    """

    _MAX_GENERATION = 0xFFFFFFFF

    def __init__(self) -> None:
        self._generation = 0

    @property
    def generation(self) -> int:
        """返回当前播报代数。"""

        return self._generation

    def cancel(self) -> None:
        """让当前及之前捕获的播报代数全部失效。"""

        self._generation = (
            self._generation + 1
        ) & self._MAX_GENERATION

    def is_stale(self, generation: int) -> bool:
        """判断捕获的代数是否已被新的事件超越。"""

        if not isinstance(generation, int) or isinstance(
            generation,
            bool,
        ):
            raise TypeError("generation必须是整数。")

        return generation != self._generation

    def new_response(self) -> None:
        """开始新播报，并使之前的播报代数失效。"""

        self.cancel()

    def reset(self) -> None:
        """把取消范围恢复到初始代数。"""

        self._generation = 0
