"""实验室会话完整流程演示：方案驱动 + 试剂安全提示 + 确定性追问 + 偏差预警。

全程离线：不使用麦克风、ASR、LLM、TTS 或网络。
学生口述用固定 ExperimentEntities 模拟（真实运行时由 ASR + LLM 抽取产出）。

运行：
    $env:PYTHONPATH='.'
    .\\.venv\\Scripts\\python.exe -B scripts\\demo_lab_session.py
"""

from __future__ import annotations

from src.config import PROJECT_DIR
from src.core.protocol_segment_evaluation import evaluate_segment
from src.core.protocol_selection import select_protocol
from src.core.protocol_session import ProtocolSessionState
from src.llm.schemas import ExperimentEntities
from src.storage.hazmat_store import HazmatStore
from src.storage.protocol_store import ProtocolStore


PROTOCOL_FILE = (
    PROJECT_DIR / "data" / "protocols" / "undergraduate_basic_protocols.json"
)

LINE = "=" * 68


def show_safety(store: HazmatStore, step) -> None:
    """在学生动手前播报本步骤涉及试剂的高危提示。

    只播报 critical 类别，避免警告过载导致学生整体忽略。
    """

    reagents = store.find_in_text(step.instruction, *step.terms)
    if not reagents:
        return

    critical = [r for r in reagents if r.is_critical]
    if not critical:
        names = "、".join(r.name_zh for r in reagents)
        print(f"  🧪 涉及试剂：{names}（无高危项）")
        return

    print("  ⚠️  安全提示（动手前请确认）：")
    for reagent in critical:
        statements = "；".join(s.text for s in reagent.critical_statements())
        cas = reagent.cas or "CAS未获取"
        print(f"      · {reagent.name_zh}（{cas}）：{statements}")
        codes = "/".join(reagent.critical_codes)
        print(f"        GHS {codes}　来源 PubChem，未经安全负责人复核")


def show_step_plan(step) -> None:
    if step.protocol_values:
        planned = "、".join(f"{k}={v}" for k, v in step.protocol_values.items())
        print(f"  📋 方案规定：{planned}")
    if step.must_record:
        print(f"  ✍️  现场必须记录：{'、'.join(step.must_record)}")
    if step.hazard_note:
        print(f"  📌 方案自带提示：{step.hazard_note}")


def speak(state, entities: ExperimentEntities, said: str) -> None:
    """模拟一次学生口述，并显示系统的确定性判断。"""

    print(f"  🗣  学生：{said}")
    result = evaluate_segment(state, entities)
    if result.follow_up_required:
        print(f"  🔊 助手追问：{result.follow_up_question}")
    else:
        print("  ✅ 本步现场记录已完整，无需追问")
    for deviation in result.deviations:
        print(
            f"  ⚠️  偏差：{deviation.field_name} 实际为 {deviation.actual_value}，"
            f"方案规定为 {deviation.protocol_value} —— 请确认是否有意调整"
        )


def main() -> None:
    protocol_store = ProtocolStore(PROTOCOL_FILE)
    hazmat = HazmatStore()

    selection = select_protocol(protocol_store, "acid-base-titration-naoh-hcl")
    state = ProtocolSessionState.start(selection)
    protocol = selection.protocol

    print(LINE)
    print("  实验室语音助手 · 完整流程演示（离线，无麦克风/LLM/网络）")
    print(LINE)
    print(f"已选实验方案：{protocol.title}")
    print(f"方案来源：{protocol.source}　版本：{protocol.version}　共 {len(protocol.steps)} 步")
    print(f"安全数据：{hazmat.authority_note}")
    print()

    # ---- 第1步：高危试剂 + 缺失追问 ----
    step = state.current_step()
    print(f"[步骤 {step.step_number}/{len(protocol.steps)}] {step.title}")
    print(f"  {step.instruction}")
    show_safety(hazmat, step)
    show_step_plan(step)
    speak(state, ExperimentEntities(action="润洗"), "我先润洗一下滴定管")
    speak(
        state,
        ExperimentEntities(action="润洗", object="氢氧化钠标准溶液",
                           instrument="碱式滴定管", observation="管壁挂液均匀，无气泡"),
        "用氢氧化钠标准溶液润洗了三次，管壁挂液均匀没有气泡",
    )

    # ---- 第2步 ----
    state = state.next()
    step = state.current_step()
    print()
    print(f"[步骤 {step.step_number}/{len(protocol.steps)}] {step.title}")
    print(f"  {step.instruction}")
    show_safety(hazmat, step)
    show_step_plan(step)
    speak(
        state,
        ExperimentEntities(object="盐酸待测液", instrument="移液管",
                           amount_value="25.00", amount_unit="mL"),
        "用移液管准确移取了25.00毫升盐酸待测液",
    )

    # ---- 第3步：致癌试剂提醒 ----
    state = state.next()
    step = state.current_step()
    print()
    print(f"[步骤 {step.step_number}/{len(protocol.steps)}] {step.title}")
    print(f"  {step.instruction}")
    show_safety(hazmat, step)
    show_step_plan(step)
    speak(state, ExperimentEntities(object="酚酞指示剂"), "加了酚酞指示剂")

    # ---- 第4步：偏差场景 ----
    state = state.jump_to(4)
    step = state.current_step()
    print()
    print(f"[步骤 {step.step_number}/{len(protocol.steps)}] {step.title}")
    print(f"  {step.instruction}")
    show_safety(hazmat, step)
    show_step_plan(step)
    speak(
        state,
        ExperimentEntities(action="滴定", object="氢氧化钠标准溶液",
                           concentration="0.1050 mol/L"),
        "用0.1050摩尔每升的氢氧化钠标准溶液滴定",
    )

    # ---- 自由模式对照 ----
    print()
    print(LINE)
    print("  对照：未选择方案（自由记录模式）")
    print(LINE)
    free_state = ProtocolSessionState.start(select_protocol(protocol_store, None))
    print(f"  当前步骤：{free_state.current_step()}")
    speak(free_state, ExperimentEntities(action="滴定"), "我开始滴定了")
    print("  → 无方案时不产生任何方案性追问或偏差，旧的自由记录能力完整保留")

    print()
    print(LINE)
    print("  演示结束。真实运行时：口述来自麦克风+ASR，实体来自LLM抽取，")
    print("  追问与安全提示将通过 TTS 播报，事件落盘到 results/*.jsonl。")
    print(LINE)


if __name__ == "__main__":
    main()
