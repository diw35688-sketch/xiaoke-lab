# -*- coding: utf-8 -*-
"""按步骤累积现场记录与偏差，输出确定性的步骤状态。

设计原则（与 src/core 领域层一致）：
- 本模块是纯逻辑：不访问文件、网络、数据库或大模型，可独立单元测试。
- "步骤完成"的判定只由确定性规则决定，大模型只负责输出"用户说了什么"这个事实，
  不直接改状态。
- 完成条件（2026-08-17 用户产品决策）：
    completed = 必测字段全部记录 或 用户手动确认（手动确认视为人类责任确认）
- 状态取值与移动端 Card 规格对齐：
    completed    本步现场必测字段全部记录（或已手动确认）且无偏差（打勾 ✓）
    error        本步出现过与方案不符的偏差（需要处理）
    waiting_user 尚未记齐，等你操作
"""

from __future__ import annotations

STATUS_COMPLETED = "completed"
STATUS_ERROR = "error"
STATUS_WAITING = "waiting_user"


class StepProgress:
    """一个实验会话内的逐步进度追踪器。

    按 step_number 累积三样东西：
    - recorded：本步已从用户口述中记录到的实体字段名集合（只收非空值）；
    - deviations：本步是否出现过偏差（一旦出现即标记，直到会话重置）；
    - confirmed：用户手动确认完成的步骤（手动完成直接打勾，不要求补口述）。

    会话切换方案时必须 reset()，否则旧方案的记录会污染新方案。
    """

    def __init__(self) -> None:
        self._recorded: dict[int, set[str]] = {}
        self._deviations: set[int] = set()
        self._confirmed: set[int] = set()

    def record(self, step_number: int, fields: dict | None, has_deviation: bool) -> None:
        """登记一段口述：fields 为 {字段名: 值}，只累加非空值的字段名。"""
        if step_number is None:
            return
        if fields:
            for name, value in fields.items():
                if value:
                    self._recorded.setdefault(step_number, set()).add(name)
        if has_deviation:
            self._deviations.add(step_number)

    def confirm(self, step_number: int) -> None:
        """用户手动确认完成：直接打勾，同时清除未处理偏差（人类责任确认）。"""
        if step_number is None:
            return
        self._confirmed.add(step_number)
        self._deviations.discard(step_number)

    def status_for(self, step) -> str:
        """按确定性规则给出某一步的状态；step 需有 step_number 与 must_record。"""
        if step.step_number in self._confirmed:
            # 手动确认优先：用户点了"完成本步"就是完成。
            return STATUS_COMPLETED
        must = set(getattr(step, "must_record", ()) or ())
        if step.step_number in self._deviations:
            # 偏差优先于完成：有偏差必须先处理，不能打勾。
            return STATUS_ERROR
        if not must.issubset(self._recorded.get(step.step_number, set())):
            return STATUS_WAITING
        # must_record 为空表示本步没有现场必测项，视为天然完成。
        return STATUS_COMPLETED

    def recorded_fields(self, step_number: int) -> list:
        """本步已经记录到的字段名（排序后返回，便于展示与测试）。"""
        return sorted(self._recorded.get(step_number, set()))

    def missing_fields(self, step) -> list:
        """本步还缺的必测字段名（排序后返回）；已手动确认的步骤视为不缺。"""
        if step.step_number in self._confirmed:
            return []
        must = set(getattr(step, "must_record", ()) or ())
        return sorted(must - self._recorded.get(step.step_number, set()))

    def reset(self) -> None:
        self._recorded.clear()
        self._deviations.clear()
        self._confirmed.clear()

    def restore(self, step_number: int, recorded: list | None, deviation: bool) -> None:
        """从持久层恢复一步的进度；recorded 为字段名列表。"""
        if step_number is None:
            return
        self._recorded[step_number] = set(recorded or [])
        if deviation:
            self._deviations.add(step_number)
        else:
            self._deviations.discard(step_number)


def card_type_for(status: str, must_record) -> str:
    """由确定性状态推导卡片类型（前端只照着渲染，不做判断）。

    - error    → error（需要处理）
    - completed→ result（结果/已完成）
    - 无必测项 → confirm（确认类，预留给未来确认流）
    - 其余     → action（等用户操作/口述）
    processing 是前端在"AI 处理中"的瞬时态，由前端自行展示。
    """
    if status == STATUS_ERROR:
        return "error"
    if status == STATUS_COMPLETED:
        return "result"
    if not (must_record or ()):
        return "confirm"
    return "action"
