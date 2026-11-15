"""Sessions Claude Code doesn't report to Anthropic (DISABLE_TELEMETRY or
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC set): vawr logs them, Anthropic doesn't count
them (work/results/telemetry_off_*.json). More in the log than Anthropic counted isn't
hidden work, so it doesn't fail, but it keeps a report from VERIFIED and says why."""
import json
import os
import tempfile
import unittest
from datetime import timedelta

from test_bundle_team import NOW, SESSIONS, T0, Home, cc_records, iso, write_log
from vawr import bundle, check, configure, daily, team

ONLY_NONINTERACTIVE = {"non-interactive": (1, {"claude-sonnet-5-5": 150})}  # s2 (xterm) went uncounted


class UncountedTest(Home):
    def sessions(self, cells):
        write_log(self.log, SESSIONS)
        return daily.check(None, "apikey_k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"],
                           now=NOW, key_name="grant key", fetch=lambda d: cc_records(cells))

    def test_a_logged_session_anthropic_did_not_count_is_uncounted_not_failed(self):
        res = self.sessions(ONLY_NONINTERACTIVE)
        self.assertEqual(res["days"][0]["status"], "uncounted")
        self.assertEqual([c["status"] for c in res["days"][0]["by_terminal"]], ["pass", "uncounted"])
        self.assertIsNone(res["ok"])
        self.assertEqual(res["uncounted_days"], ["2026-11-13"])
        self.assertIn("DISABLE_TELEMETRY", daily.uncounted_text(res))

    def test_a_hidden_session_still_fails_beside_an_uncounted_one(self):
        # Anthropic counted a non-interactive session the log lacks; the log's xterm one wasn't counted
        res = self.sessions({"non-interactive": (2, {"claude-sonnet-5-5": 250})})
        self.assertIs(res["ok"], False)
        self.assertEqual(res["days"][0]["status"], "fail")
        self.assertEqual(res["uncounted_days"], [])

    def stand_in(self, sessions):
        res = {"window": [iso(T0), iso(T0 + timedelta(hours=1))], "chain": {"ok": True, "entries": 0, "head": ""},
               "coverage": {"ok": None, "local_requests": 0, "logged_requests_in_window": 0,
                            "token_mismatches": 0, "unlogged_sessions": []},
               "bill": {"ok": True, "gaps": [], "log_excess": [], "provider_tokens": {"input": 180},
                        "background_tokens": {"input": 0}},
               "sessions": sessions, "level": "provider"}
        real = check.run
        check.run = lambda *a, **k: res
        self.addCleanup(setattr, check, "run", real)

    def test_receive_stops_at_consistent_and_says_why(self):
        sess = self.sessions(ONLY_NONINTERACTIVE)
        path = self.make("a.zip", only_projects=["grant"])
        self.stand_in(sess)
        out = bundle.receive(path, admin_key="x", ledger=self.ledger)
        self.assertEqual(out["verdict"], "consistent")
        text = bundle.render_receive(out)
        self.assertIn("NOTE  sessions", text)
        self.assertIn("DISABLE_TELEMETRY", text)
        self.assertNotIn("add your Admin key", text)
        self.assertIn("could not confirm", bundle.receive_html(out))

    def test_team_marks_the_key_for_a_check(self):
        sess_cells = ONLY_NONINTERACTIVE
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", only_projects=["grant"])
        minute = lambda m: iso(T0 + timedelta(minutes=m))  # noqa: E731
        tok = lambda n: {"input": n, "output": 0, "cache_read": 0, "cache_creation": 0}  # noqa: E731
        org = {"apikey_k1": {minute(1): {"claude-sonnet-5-5": tok(100)}, minute(2): {"claude-sonnet-5-5": tok(50)},
                             minute(5): {"claude-haiku-5-5": tok(30)}}}
        res = team.run([path], None, ledger=self.ledger, org_minutes=org,
                       keys=[{"id": "apikey_k1", "name": "grant key"}], fetch=lambda d: cc_records(sess_cells),
                       now=NOW)
        row = res["keys"][0]
        self.assertEqual(row["status"], "check")
        self.assertIn("DISABLE_TELEMETRY", row["note"])


class TelemetryOffSettingsTest(unittest.TestCase):
    def test_shell_and_user_settings(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "settings.json")
            with open(p, "w") as fh:
                json.dump({"env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "0"}}, fh)
            self.assertEqual(configure.telemetry_off_settings({"DISABLE_TELEMETRY": "true"}, p),
                             ["DISABLE_TELEMETRY in the shell", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC in %s" % p])
            self.assertEqual(configure.telemetry_off_settings({"DISABLE_TELEMETRY": ""}, os.path.join(d, "no.json")),
                             [])
            self.assertIn("CONSISTENT", configure.telemetry_off_warning({}, p))
            self.assertEqual(configure.telemetry_off_warning({}, os.path.join(d, "no.json")), "")


if __name__ == "__main__":
    unittest.main()
