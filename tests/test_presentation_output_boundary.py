# -*- coding: utf-8 -*-
"""PRESENT-DELIVERY-BOUNDARY-01 架构护栏：唯一输出权与纯函数边界。"""

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RUNTIME_MODULES = (
    "src/main.py",
    "src/asr/sensevoice_backend.py",
    "src/audio/recorder.py",
    "src/audio/vad_recorder.py",
    "src/wakeword/detector.py",
    "src/core/state_manager.py",
    "src/llm/client.py",
)

PRESENTATION_MODULES = (
    "src/core/presentation_intent.py",
    "src/core/presentation_copy.py",
    "src/core/presentation_coordinator.py",
    "src/core/presentation_projection.py",
    "src/core/presentation_pump.py",
    "src/core/terminal_renderer.py",
)

# 这些层必须是纯函数/纯数据，不允许 I/O。
PURE_PRESENTATION_MODULES = (
    "src/core/presentation_copy.py",
    "src/core/presentation_projection.py",
    "src/core/terminal_renderer.py",
)


def _ast_for(relative_path: str) -> ast.AST:
    return ast.parse(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    )


def _imported_module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
    return names


def _direct_call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        ):
            names.add(node.func.id)
    return names


class PresentationOutputBoundaryTests(unittest.TestCase):
    def test_runtime_modules_do_not_call_print_directly(self):
        violations = []
        for relative_path in RUNTIME_MODULES:
            tree = _ast_for(relative_path)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                ):
                    violations.append(f"{relative_path}:{node.lineno}")

        self.assertEqual(
            violations,
            [],
            "生产运行路径不得直接 print，应使用 PRESENT 或 logging："
            + ", ".join(violations),
        )

    def test_presentation_modules_do_not_call_print_directly(self):
        violations = []
        for relative_path in PRESENTATION_MODULES:
            tree = _ast_for(relative_path)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                ):
                    violations.append(f"{relative_path}:{node.lineno}")

        self.assertEqual(
            violations,
            [],
            "PRESENT 各层不得直接 print；唯一 stdout 写入点应是 pump 的 output 依赖："
            + ", ".join(violations),
        )

    def test_pure_presentation_layers_do_not_open_files_or_input(self):
        violations = []
        for relative_path in PURE_PRESENTATION_MODULES:
            tree = _ast_for(relative_path)
            calls = _direct_call_names(tree)
            for name in ("open", "input"):
                if name in calls:
                    violations.append(f"{relative_path}:{name}")

        self.assertEqual(
            violations,
            [],
            "文案/投影/终端渲染层必须是纯函数，不得做文件或交互 I/O："
            + ", ".join(violations),
        )

    def test_coordinator_and_pump_do_not_import_terminal_or_copy(self):
        cases = (
            (
                "src/core/presentation_coordinator.py",
                {"presentation_pump", "presentation_copy",
                 "presentation_projection", "terminal_renderer"},
            ),
            (
                "src/core/presentation_pump.py",
                {"presentation_copy", "presentation_projection",
                 "terminal_renderer"},
            ),
        )
        for relative_path, forbidden in cases:
            imported = _imported_module_names(_ast_for(relative_path))
            leaked = {
                name
                for name in imported
                if name in forbidden
                or name.startswith("src.core.terminal_renderer")
                or name.startswith("src.core.presentation_copy")
            }
            self.assertEqual(
                leaked,
                set(),
                f"{relative_path} 不得反向依赖终端渲染或文案层：{leaked}",
            )


if __name__ == "__main__":
    unittest.main()
