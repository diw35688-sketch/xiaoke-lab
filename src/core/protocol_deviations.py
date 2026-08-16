"""实验方案目标值与现场实测值的纯字符串偏差检测。"""

from __future__ import annotations

from dataclasses import dataclass, fields

from src.core.protocol import ProtocolError, ProtocolStep
from src.llm.schemas import ExperimentEntities


@dataclass(frozen=True)
class ProtocolDeviation:
    field_name: str
    protocol_value: str
    actual_value: str


def detect_protocol_deviations(
    step: ProtocolStep,
    actual_entities: ExperimentEntities,
) -> tuple[ProtocolDeviation, ...]:
    """返回现场值与方案值字符串不完全相等的字段；不做单位/数值归一化。

    检查范围是**所有带方案目标值的字段**，而不只是 ``must_record``。
    偏差最常发生在方案已规定的参数上（例如方案写 0.1000 mol/L、学生用了
    0.1050 mol/L），这类字段通常只出现在 ``protocol_values`` 中；若只遍历
    ``must_record`` 会漏报，并与 ``materialize_field_values`` 的 DEVIATION
    判定相互矛盾。

    输出顺序固定为 ``ExperimentEntities`` 的字段声明顺序，与方案 JSON 的
    键顺序无关，保证结果可复现。
    """

    if not isinstance(step, ProtocolStep):
        raise ProtocolError("step必须是ProtocolStep。")
    if not isinstance(actual_entities, ExperimentEntities):
        raise ProtocolError("actual_entities必须是ExperimentEntities。")
    deviations: list[ProtocolDeviation] = []
    for field_info in fields(ExperimentEntities):
        field_name = field_info.name
        protocol_value = step.protocol_values.get(field_name)
        actual_value = getattr(actual_entities, field_name)
        if protocol_value is None or actual_value is None:
            continue
        if isinstance(actual_value, str) and not actual_value.strip():
            continue
        if actual_value != protocol_value:
            deviations.append(
                ProtocolDeviation(field_name, protocol_value, actual_value)
            )
    return tuple(deviations)
