import subprocess
import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
