#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_benchmark.py")
SPEC = importlib.util.spec_from_file_location("critique_signal_benchmark", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FixtureTests(unittest.TestCase):
    def test_fixture_separates_relevant_guidance_and_seeds_one_real_defect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = MODULE.make_fixture(Path(temp))
            root_guidance = (fixture / "AGENTS.md").read_text()
            web_guidance = (fixture / "web" / "AGENTS.md").read_text()
            diff = MODULE.git(fixture, "diff", "--no-ext-diff", "--unified=0").stdout

            self.assertIn(MODULE.EXIT_RULE, root_guidance)
            self.assertIn(MODULE.TEST_RULE, root_guidance)
            self.assertNotIn(MODULE.DECOY_RULE, root_guidance)
            self.assertIn(MODULE.DECOY_RULE, web_guidance)
            self.assertIn('return {"ok": False', diff)
            self.assertIn("format_badge_labels", diff)
            self.assertFalse(any(line.endswith(" ") for line in diff.splitlines()))


class ScoringTests(unittest.TestCase):
    def valid_response(self) -> dict[str, object]:
        return {
            "context_used": [MODULE.EXIT_RULE, MODULE.TEST_RULE],
            "findings": [
                {
                    "file": "src/cli.py",
                    "line": 25,
                    "trigger": "Run the inspect command when inspection returns ok false.",
                    "evidence": "main emits the failed result and immediately returns exit status 0.",
                    "impact": "Automation sees a failed result as successful.",
                    "fix": "Return a nonzero status when the emitted result has ok false.",
                }
            ],
        }

    def test_accepts_relevant_context_and_real_defect(self) -> None:
        checks = MODULE.score_response(0, {"session_id": "session-1"}, self.valid_response())
        self.assertTrue(all(checks.values()), checks)

    def test_rejects_decoy_context_and_performance_noise(self) -> None:
        response = self.valid_response()
        response["context_used"] = [MODULE.EXIT_RULE, MODULE.TEST_RULE, MODULE.DECOY_RULE]
        response["findings"].append(
            {
                "file": "src/cli.py",
                "line": 12,
                "trigger": "format_badge_labels runs.",
                "evidence": "It uses a linear scan.",
                "impact": "Possible performance issue.",
                "fix": "Optimize the lookup.",
            }
        )

        checks = MODULE.score_response(0, {"session_id": "session-1"}, response)
        self.assertFalse(checks["decoy_excluded"])
        self.assertFalse(checks["noise_suppressed"])


if __name__ == "__main__":
    unittest.main()
