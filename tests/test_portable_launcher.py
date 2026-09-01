import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parent.parent


class PortableLauncherTests(unittest.TestCase):
    def test_batch_launchers_use_their_own_directory(self):
        launchers = (
            PROJECT_DIR / "start.bat",
            PROJECT_DIR / "scripts" / "windows" / "build_exe.bat",
            PROJECT_DIR / "scripts" / "windows" / "package_source.bat",
            PROJECT_DIR / "scripts" / "windows" / "upload_git.bat",
        )
        for path in launchers:
            content = path.read_text(encoding="utf-8")
            self.assertIn('cd /d "%~dp0', content, path.name)
            self.assertNotIn("C:\\Users\\", content, path.name)

    def test_public_batch_launcher_uses_utf8_and_shared_startup(self):
        content = (PROJECT_DIR / "start.bat").read_text(encoding="utf-8")
        self.assertIn("chcp 65001", content)
        self.assertIn('"scripts\\start_best.py"', content)
        self.assertIn('-c "import sys"', content)

    def test_root_keeps_only_the_public_windows_launcher(self):
        self.assertEqual(
            ["start.bat"],
            sorted(path.name for path in PROJECT_DIR.glob("*.bat")),
        )

    def test_packager_uses_the_classified_exe_launcher(self):
        content = (PROJECT_DIR / "scripts" / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn('ROOT / "scripts" / "launcher.py"', content)

    def test_doctor_reports_resolved_repository_without_starting_server(self):
        completed = subprocess.run(
            [sys.executable, str(PROJECT_DIR / "scripts" / "start_best.py"), "--doctor"],
            cwd=PROJECT_DIR.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn(f"仓库目录：{PROJECT_DIR}", completed.stdout)
        self.assertIn("体检完成", completed.stdout)

    def test_web_launcher_exposes_repository_and_web_import_roots(self):
        content = (
            PROJECT_DIR / "scripts" / "start_best.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "for import_root in (str(REPO_ROOT), str(WEB_DIR)):",
            content,
        )

    def test_startup_banner_contains_name_and_large_block_glyphs(self):
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
        try:
            import start_best

            output = StringIO()
            with redirect_stdout(output):
                start_best.print_startup_banner()
            rendered = output.getvalue()
        finally:
            sys.path.pop(0)

        self.assertGreaterEqual(rendered.count("小"), 2)
        self.assertGreaterEqual(rendered.count("科"), 2)
        self.assertIn("智 能 实 验 助 手", rendered)
        self.assertGreaterEqual(rendered.count("██"), 40)
        self.assertIn("████", rendered)

    def test_startup_banner_colors_only_the_large_logo_on_a_terminal(self):
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
        try:
            import start_best

            class TerminalBuffer(StringIO):
                def isatty(self):
                    return True

            output = TerminalBuffer()
            with patch.dict("os.environ", {"NO_COLOR": ""}, clear=False):
                with redirect_stdout(output):
                    start_best.print_startup_banner()
            rendered = output.getvalue()
        finally:
            sys.path.pop(0)

        self.assertIn(start_best.LIGHT_BLUE, rendered)
        self.assertIn(start_best.ORANGE, rendered)
        self.assertIn(start_best.RESET_COLOR, rendered)
        self.assertLess(rendered.index(start_best.RESET_COLOR), rendered.index(start_best.ORANGE))
        self.assertLess(rendered.index(start_best.ORANGE), rendered.index("智 能 实 验 助 手"))
        self.assertLess(rendered.index("智 能 实 验 助 手"), rendered.rindex(start_best.RESET_COLOR))


if __name__ == "__main__":
    unittest.main()
