import unittest

from scripts import package


class SourcePackageContractTests(unittest.TestCase):
    def test_windows_wrapper_propagates_package_failure(self):
        wrapper = (
            package.ROOT / "scripts" / "windows" / "package_source.bat"
        ).read_text(encoding="utf-8")
        self.assertIn('set "package_exit_code=%errorlevel%"', wrapper)
        self.assertIn("exit /b %package_exit_code%", wrapper)

    def test_required_public_files_are_not_excluded(self):
        for path in (
            "start.bat",
            "README.md",
            ".env.example",
            "scripts/windows/package_source.bat",
            "scripts/launcher.py",
        ):
            self.assertFalse(package.should_skip(path), path)

    def test_machine_specific_and_sensitive_files_are_excluded(self):
        for path in (
            ".env",
            ".runtime-python311.zip",
            ".runtime-python311/python.exe",
            "web/settings.json",
            "web/lab_agent.db",
            "web/uvicorn-voice.out.log",
            "src/__pycache__/module.pyc",
        ):
            self.assertTrue(package.should_skip(path), path)

    def test_runtime_data_directories_are_pruned(self):
        names = [
            ".runtime-python311",
            ".venv",
            "audio",
            "results",
            "scripts",
        ]
        package.prune_dirs(package.ROOT, names)
        self.assertEqual(["audio", "scripts"], names)

        audio_names = ["raw", "recordings", "wav"]
        package.prune_dirs(package.ROOT / "audio", audio_names)
        self.assertEqual(["wav"], audio_names)


if __name__ == "__main__":
    unittest.main()
