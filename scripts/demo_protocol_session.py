"""方案驱动会话离线演示。

只使用本地方案库和固定的实体输入，不访问麦克风、ASR、LLM或网络。
"""

from __future__ import annotations

from pathlib import Path

from src.core.protocol_segment_evaluation import evaluate_segment
from src.core.protocol_selection import select_protocol
from src.core.protocol_session import ProtocolSessionState
from src.llm.schemas import ExperimentEntities
from src.storage.protocol_store import ProtocolStore


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"


def show_evaluation(label: str, evaluation) -> None:
    print(f"{label}：")
    print(f"  缺失现场字段：{evaluation.missing_fields or '无'}")
    print(f"  追问：{evaluation.follow_up_question or '无'}")
    if evaluation.deviations:
        for deviation in evaluation.deviations:
            print(
                "  偏差提示："
                f"{deviation.field_name}实际为{deviation.actual_value}，"
                f"方案规定为{deviation.protocol_value}。"
            )
    else:
        print("  偏差：无")


def main() -> None:
    store = ProtocolStore(PROTOCOL_PATH)
    selection = select_protocol(store, 1)
    state = ProtocolSessionState.start(selection)
    protocol = selection.protocol
    assert protocol is not None

    print("=" * 68)
    print("方案驱动会话离线演示（固定实体输入，不使用麦克风/LLM/网络）")
    print(f"选择方案：{protocol.title}")
    print(f"步骤总数：{len(protocol.steps)}")
    print("=" * 68)

    for _ in range(2):
        step = state.current_step()
        assert step is not None
        print()
        print(f"[步骤 {step.step_number}/{len(protocol.steps)}] {step.title}")
        print(f"  方案规定值：{dict(step.protocol_values) or '无'}")
        print(f"  现场必测字段：{step.must_record or '无'}")

        spoken_entities = (
            ExperimentEntities(action="称量", object="磷酸二氢盐和磷酸氢二盐", amount_unit="g")
            if step.step_number == 1
            else ExperimentEntities(action="溶解", object="磷酸盐")
        )
        evaluation = evaluate_segment(state, spoken_entities)
        show_evaluation("学生口述（模拟）", evaluation)

        completed_entities = (
            ExperimentEntities(
                action="称量",
                object="磷酸二氢盐和磷酸氢二盐",
                amount_value="3.58",
                amount_unit="g",
            )
            if step.step_number == 1
            else ExperimentEntities(
                action="溶解",
                object="磷酸盐",
                observation="粉末完全溶解，溶液澄清",
            )
        )
        show_evaluation("学生补充", evaluate_segment(state, completed_entities))
        state = state.next()

    print()
    print("[偏差场景]")
    state = ProtocolSessionState.start(selection)
    deviation = evaluate_segment(state, ExperimentEntities(amount_value="3.61"))
    show_evaluation("学生说实际称量3.61克", deviation)

    print()
    print("[自由模式对照]")
    free_state = ProtocolSessionState.start(select_protocol(store, None))
    free_result = evaluate_segment(
        free_state,
        ExperimentEntities(amount_value="3.61", observation="白色粉末"),
    )
    show_evaluation("同样的口述在无方案下", free_result)


if __name__ == "__main__":
    main()
