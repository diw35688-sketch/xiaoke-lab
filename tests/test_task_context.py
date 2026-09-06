# -*- coding: utf-8 -*-
"""任务层上下文合同测试。

背景（2026-08-30）：统一理解器此前只有 5 个上下文字段，看不到方案与当前步骤；
`domain.step_view()` 的结果只喂给前端画卡片。模型因此在"不知道你在做什么"的
前提下分类，听错术语、认不出指代——这是"聊天很费劲"的主因。

这套测试锁三件事：
1. 任务层能从 step_view 正确构造，且结构异常时安全退回自由模式（不得让整轮失败）；
2. 任务层确实进入提示词，且自由模式不占提示词预算；
3. **加上下文引入的新风险被堵住**：模型不得把方案预期值当作已发生的事实。
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from src.core.task_context import TaskContext
from src.core.unified_prompts import (
    UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
    build_unified_understanding_user_prompt,
)
from src.core.unified_understanding import UnifiedUnderstandingInput


def _view(**overrides):
    step = {
        "number": 3, "title": "加缓冲液", "instruction": "加入 5 mL PBS",
        "protocol_values": {"amount_value": "5", "amount_unit": "mL"},
        "must_record": ["amount_value", "amount_unit"],
        "recorded": ["amount_unit"], "missing": ["amount_value"],
        "hazard_note": "注意腐蚀", "terms": ["PBS", "磷酸缓冲液"],
    }
    step.update(overrides.pop("step", {}))
    view = {
        "mode": "protocol",
        "protocol": {"title": "PBS 配制", "total_steps": 5, "id": "p1", "version": "1"},
        "step": step,
    }
    view.update(overrides)
    return view


class TaskContextBuildTests(unittest.TestCase):
    def test_parses_protocol_step(self):
        ctx = TaskContext.from_step_view(_view())
        self.assertFalse(ctx.is_free)
        self.assertEqual(ctx.protocol_title, "PBS 配制")
        self.assertEqual(ctx.step_number, 3)
        self.assertEqual(ctx.total_steps, 5)
        self.assertEqual(dict(ctx.expected_values), {"amount_value": "5", "amount_unit": "mL"})
        self.assertEqual(ctx.must_record, ("amount_value", "amount_unit"))
        self.assertEqual(ctx.missing_fields, ("amount_value",))
        self.assertEqual(ctx.terms, ("PBS", "磷酸缓冲液"))

    def test_free_mode_view(self):
        self.assertTrue(TaskContext.from_step_view(
            {"mode": "free", "protocol": None, "step": None}).is_free)

    def test_malformed_views_degrade_to_free_never_raise(self):
        # 任务层缺失只该让模型少知道一点，绝不能让一次口述整轮失败。
        for bad in (None, {}, {"mode": "protocol"}, {"mode": "protocol", "step": None},
                    _view(step={"number": "x"}), _view(step={"number": 0}),
                    _view(protocol={"title": "  ", "total_steps": 5})):
            with self.subTest(bad=bad):
                self.assertTrue(TaskContext.from_step_view(bad).is_free)

    def test_blank_fields_are_dropped_not_emitted_as_empty(self):
        ctx = TaskContext.from_step_view(
            _view(step={"hazard_note": "   ", "terms": ["", "  ", "PBS", "PBS"]}))
        self.assertIsNone(ctx.hazard_note)
        self.assertEqual(ctx.terms, ("PBS",), "空白应剔除且去重")

    def test_protocol_mode_requires_identity(self):
        with self.assertRaises(ValueError):
            TaskContext(mode="protocol", step_number=None, protocol_title="x")
        with self.assertRaises(ValueError):
            TaskContext(mode="bogus")


class TaskContextPromptTests(unittest.TestCase):
    def _prompt(self, ctx):
        return build_unified_understanding_user_prompt(UnifiedUnderstandingInput(
            raw_text="加了缓冲液", session_active=True, session_id="s1",
            segment_id=1, task_context=ctx))

    def test_free_mode_costs_no_prompt_budget(self):
        self.assertNotIn("task_context", self._prompt(TaskContext.free()))

    def test_protocol_context_reaches_the_prompt(self):
        text = self._prompt(TaskContext.from_step_view(_view()))
        for token in ("task_context", "PBS 配制", "step_number", "glossary", "expected_values"):
            self.assertIn(token, text, f"提示词应包含 {token}")

    def test_default_input_is_free(self):
        request = UnifiedUnderstandingInput(
            raw_text="x", session_active=True, session_id="s", segment_id=1)
        self.assertTrue(request.task_context.is_free, "旧调用方不传即自由模式")


class AntiFabricationGuardTests(unittest.TestCase):
    """加任务层引入的新风险：模型可能把方案里的数字当成用户说过的事实。

    这比听错更危险——那是拿方案编造实验记录。守则必须常驻系统提示词。
    """

    def test_prompt_forbids_treating_expected_values_as_facts(self):
        prompt = UNIFIED_UNDERSTANDING_SYSTEM_PROMPT
        self.assertIn("拿方案编造实验记录", prompt)
        self.assertIn("必须是null", prompt, "用户没说的量必须留空")
        self.assertIn("绝不", prompt)

    def test_prompt_forbids_correcting_user_values_to_protocol_values(self):
        # 偏差正是必须如实留痕的东西，不得被"纠正"掉
        self.assertIn("偏差", UNIFIED_UNDERSTANDING_SYSTEM_PROMPT)
        self.assertIn("原样记录用户说的", UNIFIED_UNDERSTANDING_SYSTEM_PROMPT)

    def test_prompt_keeps_decisions_deterministic(self):
        # 缺项/偏差/能否进下一步由 domain.evaluate_for_state 判定，模型不得代劳
        self.assertIn("由系统确定性判定", UNIFIED_UNDERSTANDING_SYSTEM_PROMPT)


class TaskContextWiringTests(unittest.TestCase):
    """接线守卫：任务层必须真的从 step_view 走到观察器。"""

    def test_experiment_processor_passes_task_context(self):
        source = (ROOT / "web" / "turn_processors.py").read_text(encoding="utf-8")
        self.assertIn("task_context=TaskContext.from_step_view(step)", source,
                      "ExperimentProcessor 必须把当前步骤传给统一理解")

    def test_observer_forwards_task_context(self):
        source = (ROOT / "src" / "core" / "unified_observer.py").read_text(encoding="utf-8")
        self.assertIn("task_context=task_context or TaskContext.free()", source)

    def test_bypass_forwards_task_context(self):
        source = (ROOT / "src" / "core" / "unified_acceptance_bypass.py").read_text(encoding="utf-8")
        self.assertIn("task_context=self.task_context", source)

    def test_end_to_end_threading(self):
        from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypassInput
        from src.core.clarification_acceptance import ClarificationContextSnapshot
        ctx = TaskContext.from_step_view(_view())
        request = UnifiedAcceptanceBypassInput(
            request_id="r1", session_id="s1", segment_id=1, asr_result=None,
            clarification_context=ClarificationContextSnapshot(unresolved=(), current_clarification_id=None),
            raw_text="加了缓冲液", task_context=ctx,
        ).to_understanding_input()
        self.assertEqual(request.task_context.step_number, 3)
        self.assertIn("PBS 配制", build_unified_understanding_user_prompt(request))


if __name__ == "__main__":
    unittest.main()
