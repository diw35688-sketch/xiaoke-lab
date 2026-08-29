import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_llm_clients.py"
SPEC = importlib.util.spec_from_file_location("compare_llm_clients", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class CompareLlmClientsScriptTests(unittest.TestCase):
    def test_default_plan_has_eighteen_calls_and_alternates_order(self):
        plan = module.build_plan(3)

        self.assertEqual(len(plan), 18)
        first_pairs = [item.client for item in plan[:2]]
        second_round_start = len(module.CASES) * 2
        second_pairs = [
            item.client for item in plan[second_round_start:second_round_start + 2]
        ]
        self.assertEqual(first_pairs, ["direct_http", "openai_sdk"])
        self.assertEqual(second_pairs, ["openai_sdk", "direct_http"])

    def test_request_fingerprint_contains_no_prompt_or_api_key(self):
        fingerprint = module.request_fingerprint(module.CASES[0], 2000)

        self.assertEqual(fingerprint["max_tokens"], 2000)
        self.assertIn("system_prompt_sha256", fingerprint)
        self.assertIn("user_prompt_sha256", fingerprint)
        self.assertNotIn("system_prompt", fingerprint)
        self.assertNotIn("user_prompt", fingerprint)
        self.assertNotIn("api_key", fingerprint)

    def test_dry_run_does_not_call_external_clients(self):
        original = module.settings_store.current

        class Settings:
            model_name = "test-model"

        module.settings_store.current = lambda: Settings()
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(module.main([]), 0)
            self.assertIn("DRY_RUN", output.getvalue())
        finally:
            module.settings_store.current = original

    def test_summary_uses_only_successful_parse_timings(self):
        rows = [
            module.CallResult(1, "measurement", "direct_http", 100, 10, "a", True, "experiment", None),
            module.CallResult(2, "measurement", "direct_http", 300, 10, "b", True, "experiment", None),
            module.CallResult(1, "measurement", "openai_sdk", 50, 0, None, False, None, "ValueError"),
        ]

        summary = {item["client"]: item for item in module.summarize(rows)}

        self.assertEqual(summary["direct_http"]["median_ms"], 200)
        self.assertEqual(summary["openai_sdk"]["failures"], 1)
        self.assertIsNone(summary["openai_sdk"]["median_ms"])


if __name__ == "__main__":
    unittest.main()
