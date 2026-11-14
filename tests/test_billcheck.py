import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from vawr import billcheck

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)  # before the test files are written
SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
BG = {"input": 300, "output": 200, "cache_read": 7010, "cache_creation": 0}


def m(i):
    return T0 + timedelta(minutes=i)


def assistant(rid, minute, n, session, model=SONNET, extra=None):
    e = {"type": "assistant", "requestId": rid, "sessionId": session,
         "timestamp": (m(minute) + timedelta(seconds=20)).isoformat().replace("+00:00", "Z"),
         "message": {"model": model, "usage": {"input_tokens": n, "output_tokens": n,
                                               "cache_read_input_tokens": 0,
                                               "cache_creation_input_tokens": 0}}}
    e.update(extra or {})
    return e


def tok(n):
    return {"input": n, "output": n, "cache_read": 0, "cache_creation": 0}


class BillCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, project, session, entries):
        d = os.path.join(self.projects, project)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, session + ".jsonl"), "w") as fh:
            for e in entries:
                fh.write(json.dumps(e) + "\n")

    def run_check(self, provider):
        return billcheck.check(m(0), m(20), provider_minutes=provider, projects=self.projects,
                               key_id="test")

    def test_everything_accounted_for(self):
        self.write("p", "s1", [assistant("r1", 3, 100, "s1")])
        res = self.run_check({m(3): {SONNET: tok(100), HAIKU: BG}})
        self.assertEqual(res["gaps"], [])
        self.assertEqual(res["log_excess"], [])
        self.assertEqual(res["background_tokens"]["cache_read"], 7010)

    def test_billed_work_with_no_local_record_is_unexplained(self):
        self.write("p", "s1", [assistant("r1", 3, 100, "s1")])
        res = self.run_check({m(3): {SONNET: tok(100), HAIKU: BG}, m(12): {SONNET: tok(500)}})
        self.assertEqual(len(res["gaps"]), 1)
        self.assertEqual(res["gaps"][0]["start"], m(12).isoformat())
        self.assertIn("Unexplained", billcheck.render(res))

    def test_subscription_sessions_never_offset_billed_usage(self):
        # a subscription session in the same minute as an unlogged key run must not hide it
        self.write("p", "s1", [assistant("r1", 3, 100, "s1")])
        self.write("q", "sub", [{"type": "session-owner"}, assistant("r2", 12, 500, "sub")])
        res = self.run_check({m(3): {SONNET: tok(100), HAIKU: BG}, m(12): {SONNET: tok(500)}})
        self.assertEqual(len(res["gaps"]), 1)
        self.assertEqual(res["local_account_requests"], 1)

    def test_usage_only_in_cost_totals_is_credited_not_flagged(self):
        # an interactive session: one listed request, plus a title (haiku) and a prompt
        # suggestion (sonnet) that only the session's cost totals include
        cost = {"type": "cost-state", "modelUsage": {
            SONNET: {"inputTokens": 100 + 400, "outputTokens": 100 + 50, "cacheReadInputTokens": 0,
                     "cacheCreationInputTokens": 0},
            HAIKU: {"inputTokens": 300, "outputTokens": 20, "cacheReadInputTokens": 0,
                    "cacheCreationInputTokens": 0}}}
        self.write("p", "s1", [assistant("r1", 3, 100, "s1"),
                               {"type": "user", "timestamp": m(6).isoformat()}, cost])
        provider = {m(3): {SONNET: tok(100), HAIKU: {"input": 300, "output": 20, "cache_read": 0,
                                                     "cache_creation": 0}},
                    m(5): {SONNET: {"input": 400, "output": 50, "cache_read": 0, "cache_creation": 0}}}
        res = self.run_check(provider)
        self.assertEqual(res["gaps"], [], res["gaps"])
        self.assertEqual(sum(res["recorded_totals_tokens"].values()), 770)

    def test_cost_totals_dont_cover_usage_outside_the_session(self):
        cost = {"type": "cost-state", "modelUsage": {SONNET: {"inputTokens": 600, "outputTokens": 100,
                                                              "cacheReadInputTokens": 0,
                                                              "cacheCreationInputTokens": 0}}}
        self.write("p", "s1", [assistant("r1", 3, 100, "s1"), cost])
        res = self.run_check({m(3): {SONNET: tok(100)}, m(15): {SONNET: {"input": 500, "output": 0,
                                                                          "cache_read": 0, "cache_creation": 0}}})
        self.assertEqual(len(res["gaps"]), 1)

    def test_keys_from_env_then_files(self):
        d = self.projects
        f1, f2 = os.path.join(d, "a.env"), os.path.join(d, "b.env")
        open(f1, "w").write("ANTHROPIC_API_KEY=from-first\n")
        open(f2, "w").write("export ANTHROPIC_ADMIN_KEY='from-second'\nANTHROPIC_API_KEY=ignored\n")
        self.assertEqual(billcheck.admin_and_key(env={}, files=[f1, f2]), ("from-second", "from-first"))
        self.assertEqual(billcheck.admin_and_key(env={"ANTHROPIC_API_KEY": "env"}, files=[f1])[1], "env")

    def test_parse_when(self):
        now = T0
        self.assertEqual(billcheck.parse_when("90m", now), T0 - timedelta(minutes=90))
        self.assertEqual(billcheck.parse_when("2d", now), T0 - timedelta(days=2))
        self.assertEqual(billcheck.parse_when("2026-11-14T08:00", now), datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
