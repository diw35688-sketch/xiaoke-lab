# -*- coding: utf-8 -*-
"""SYNC-UI-CLAIMS-01 守护测试：用户可见文案不得承诺不存在的行为。"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 这些文案曾与真实行为不一致，永远不得回到生产代码。
FORBIDDEN_PHRASES = (
    "旧流程继续",
    "系统将立即继续监听",
    "立即继续监听",
    "提交 M 段实验口述",
    "提交 0 段实验口述",
)

# 只在有对应实现时允许存在的承诺。
REQUIRED_TRUTHFUL_PHRASES = {
    "src/main.py": (
        "现在可以连续口述，无需等待 LLM 处理完成。",
        "当前实验会话仍然有效，系统将继续监听。",
    ),
}


class UiClaimsTests(unittest.TestCase):
    def test_forbidden_phrases_are_absent_from_user_facing_source(self):
        scanned_files = (
            "src/main.py",
            "src/core/presentation_copy.py",
            "src/core/presentation_projection.py",
            "src/core/terminal_renderer.py",
            "src/core/presentation_intent.py",
        )
        for rel in scanned_files:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for phrase in FORBIDDEN_PHRASES:
                self.assertNotIn(
                    phrase,
                    text,
                    f"{rel} 中出现了与真实行为不符的历史文案：{phrase!r}",
                )

    def test_nonblocking_claim_is_backed_by_ordered_task_queue(self):
        main_text = (ROOT / "src/main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "现在可以连续口述，无需等待 LLM 处理完成。",
            main_text,
        )
        self.assertTrue(
            (ROOT / "src/core/ordered_task_queue.py").is_file(),
            "非阻塞承诺需要 OrderedTaskQueue 实现支撑。",
        )

    def test_required_truthful_phrases_exist(self):
        for rel, phrases in REQUIRED_TRUTHFUL_PHRASES.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            for phrase in phrases:
                self.assertIn(phrase, text, f"{rel} 缺少 {phrase!r}")


if __name__ == "__main__":
    unittest.main()
