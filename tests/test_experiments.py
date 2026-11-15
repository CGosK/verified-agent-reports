"""The research harness added on Nov 14-15: hidden tests, runner overrides, the
midnight gate, the experiment driver's dispatch, outcome columns and result rendering."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from vawr import claims, interactive, report, results, runner

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAFETY = ("s1_refusals", "s2_agreement", "s3_contamination", "s4_redact", "s5_monitor")


class HiddenTestsTest(unittest.TestCase):
    def run_hidden(self, repo, tid):
        path = os.path.join(REPO, "tasks", "hidden_tests", "test_hidden_%s.py" % tid.split("_")[0])
        r = subprocess.run([sys.executable, path], cwd=repo, env=dict(os.environ, PYTHONPATH=repo),
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0

    def test_pass_on_solutions_fail_on_stubs(self):
        tasks = {t["id"]: t for t in json.load(open(os.path.join(REPO, "tasks", "tasks.json")))}
        for tid in SAFETY:
            with tempfile.TemporaryDirectory() as d:
                repo = os.path.join(d, "repo")
                shutil.copytree(os.path.join(REPO, "tasks", "repo"), repo)
                self.assertFalse(self.run_hidden(repo, tid), tid)
                shutil.copy(os.path.join(REPO, "tasks", "solutions", tid + ".py"), os.path.join(repo, tasks[tid]["path"]))
                self.assertTrue(self.run_hidden(repo, tid), tid)

    def test_original_tests_run_against_the_worktree(self):
        task = {t["id"]: t for t in json.load(open(os.path.join(REPO, "tasks", "tasks.json")))}["s1_refusals"]
        self.assertIsNone(claims.original_test_passes("/nonexistent", task))
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "repo")
            shutil.copytree(os.path.join(REPO, "tasks", "repo"), repo)
            self.assertFalse(claims.original_test_passes(repo, task))
            shutil.copy(os.path.join(REPO, "tasks", "solutions", "s1_refusals.py"), os.path.join(repo, task["path"]))
            # an agent that edits the worktree's own test can't make the original one pass for it
            open(os.path.join(repo, "tests", "test_s1_refusals.py"), "w").write("")
            self.assertTrue(claims.original_test_passes(repo, task))


class RunnerOverridesTest(unittest.TestCase):
    def test_underperform_prompt_and_overrides(self):
        task = {"symbol": "f", "path": "p.py", "test": "tests.t"}
        self.assertIn("deliberately partial", runner.build_prompt(task, "prompt_underperform"))
        self.assertIn("prompt_underperform", runner.PLANTS)
        os.environ["VAWR_CLAUDE_BIN"] = "/x/claude"
        os.environ["VAWR_CLAUDE_CONFIG_DIR"] = "/x/config"
        try:
            self.assertEqual(runner.build_cmd("sprint", "hi", "haiku", 1.0)[0], "/x/claude")
            for mode in ("clean", "inherited"):
                env = runner.build_env("subscription", None, {"category": "other"}, "r", {}, env_mode=mode)
                self.assertEqual(env["CLAUDE_CONFIG_DIR"], "/x/config")
        finally:
            del os.environ["VAWR_CLAUDE_BIN"], os.environ["VAWR_CLAUDE_CONFIG_DIR"]
        self.assertEqual(runner.build_cmd("sprint", "hi", "haiku", 1.0)[0], "claude")


class MidnightGateTest(unittest.TestCase):
    def gate(self, woke):
        start = datetime(2026, 11, 15, 23, 58, tzinfo=timezone.utc)
        return interactive.midnight_test(start, now=lambda: woke)

    def test_late_or_post_midnight_wakes_are_skipped(self):
        self.assertEqual(self.gate(datetime(2026, 11, 15, 23, 58, 45, tzinfo=timezone.utc)), "skipped")
        self.assertEqual(self.gate(datetime(2026, 11, 16, 0, 0, 30, tzinfo=timezone.utc)), "skipped")

    def test_a_start_time_without_a_timezone_is_utc(self):
        naive = datetime(2026, 11, 15, 23, 58)
        self.assertEqual(interactive.midnight_test(naive, now=lambda: datetime(2026, 11, 16, 1, 0,
                                                                               tzinfo=timezone.utc)), "skipped")

    def test_unknown_arguments_start_nothing(self):
        self.assertEqual(interactive.main(["--help"]), 2)
        self.assertEqual(interactive.main([]), 2)


class OutcomeColumnTest(unittest.TestCase):
    def test_summarize_and_render(self):
        runs = claims.summarize_runs({"a": [{"verdict": "held"}], "b": [], "c": []},
                                     {"a": True, "b": False, "c": None})
        self.assertEqual([runs[k]["outcome_pass"] for k in "abc"], [True, False, None])
        rep = {"categories": [{"category": "safety", "runs": 3, "requests": 3, "total_tokens": 9, "token_share": 1.0,
                               "cost_usd": 0.0, "claims": 1, "claims_held": 1, "outcomes": 2, "outcomes_passed": 1}],
               "log": {"entries": 1, "chain_ok": True, "head": "ab"}, "note": ""}
        self.assertIn("| 1 of 2 |", report.render(rep))


class ResultsRenderTest(unittest.TestCase):
    def test_failed_full_day_is_not_described_as_success(self):
        d = tempfile.mkdtemp()
        old = results.RESULTS
        results.RESULTS = d
        try:
            json.dump({"verdict": "failed", "manifest": {"key_id": "apikey_x"},
                       "check": {"bill": {"provider_tokens": {"input": 5}, "gaps": [], "log_excess": []},
                                 "sessions": {"days": [{"day": "2026-11-14", "status": "fail", "complete": True,
                                                        "anthropic_sessions": 6, "log_sessions": 5,
                                                        "token_difference": {"m": 3}}]}}},
                      open(os.path.join(d, "daytest_received.json"), "w"))
            text = results.render()
        finally:
            results.RESULTS = old
            shutil.rmtree(d)
        self.assertIn("Verdict: failed", text)
        self.assertNotIn("every Claude Code session on it that day was logged", text)


if __name__ == "__main__":
    unittest.main()
