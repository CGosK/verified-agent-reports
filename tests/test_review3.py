"""One test per problem the third review (Nov 15) found: each fails on the code before the fix."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works with `-s tests` and `-s tests -t .`
from test_bundle_team import NOW, SESSIONS, T0, Home, cc_records, edit_json, iso, rewrite, write_log  # noqa: E402
from vawr import bundle, chainlog, team, usage_api  # noqa: E402


def minute(m):
    return iso(T0 + timedelta(minutes=m))


def tok(n):
    return {"input": n, "output": 0, "cache_read": 0, "cache_creation": 0}


class WindowBoundsTest(Home):
    def test_a_window_starting_inside_a_minute_is_refused(self):
        # a start a microsecond past 06:00 used to drop the whole 06:00 minute from the bill check
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        bad = rewrite(path, os.path.join(self.d, "sub.zip"), edit_json(
            "bundle.json", lambda m: m.update(window=[(T0 + timedelta(microseconds=1)).isoformat(),
                                                      (T0 + timedelta(hours=1)).isoformat()])))
        with self.assertRaises(ValueError) as cm:
            bundle.receive(bad, ledger=self.ledger)
        self.assertIn("whole UTC minutes", str(cm.exception))

    def test_receive_shows_the_window_in_utc(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        plus18 = timezone(timedelta(hours=18))
        shifted = rewrite(path, os.path.join(self.d, "plus18.zip"), edit_json(
            "bundle.json", lambda m: m.update(window=[T0.astimezone(plus18).isoformat(),
                                                      (T0 + timedelta(hours=1)).astimezone(plus18).isoformat()])))
        out = self.receive_verified(shifted, now=NOW)
        text = bundle.render_receive(out)
        self.assertIn("2026-11-13 06:00 to 07:00 UTC", text)
        self.assertNotIn("2026-11-14 00:00", text)


class ApiTimesTest(unittest.TestCase):
    def test_times_sent_to_the_api_are_utc(self):
        plus17 = timezone(timedelta(hours=17))
        self.assertEqual(usage_api._iso(datetime(2026, 11, 14, 17, 0, tzinfo=plus17)), "2026-11-14T00:00:00Z")
        seen = []
        real = usage_api._get
        usage_api._get = lambda key, path, params, **kw: seen.append(params) or {"data": [], "has_more": False}
        try:
            usage_api.minute_usage("x", "apikey_k1", datetime(2026, 11, 14, 17, 0, tzinfo=plus17),
                                   datetime(2026, 11, 15, 17, 0, tzinfo=plus17))
            usage_api.org_minute_usage("x", datetime(2026, 11, 14, 17, 0, tzinfo=plus17),
                                       datetime(2026, 11, 15, 17, 0, tzinfo=plus17))
        finally:
            usage_api._get = real
        self.assertTrue(seen)
        for p in seen:
            self.assertEqual(p["starting_at"], "2026-11-14T00:00:00Z")


class TeamForkTest(Home):
    def test_a_rewritten_copy_of_the_same_log_fails(self):
        # keep the first entry (so the log ID matches), then write different, larger usage
        write_log(self.log, SESSIONS)
        honest = self.make("honest.zip", only_projects=["grant"])
        fork = os.path.join(self.d, "fork.jsonl")
        first = next(chainlog.read_entries(self.log))[1]
        with open(fork, "w") as fh:
            fh.write(chainlog.canonical(first) + "\n")
        log = chainlog.ChainLog(fork)
        for e in [e for _, e in chainlog.read_entries(self.log)][1:]:
            ev = json.loads(json.dumps(e["event"]))
            a = ev.get("attributes") or {}
            if "input_tokens" in a:
                a["input_tokens"] *= 10
            log.append(ev)
        forked = self.make("fork.zip", log=fork, only_projects=["grant"])
        self.assertEqual(bundle.log_id(fork), bundle.log_id(self.log))
        org = {"apikey_k1": {minute(1): {"claude-sonnet-5-5": tok(100)}, minute(2): {"claude-sonnet-5-5": tok(50)},
                             minute(5): {"claude-haiku-5-5": tok(30)}}}
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        for order in ([honest, forked], [forked, honest]):
            res = team.run(order, None, ledger=self.ledger, org_minutes=org,
                           keys=[{"id": "apikey_k1", "name": "grant key"}], fetch=lambda d: recs, now=NOW)
            row = res["keys"][0]
            self.assertEqual(row["status"], "fail", team.render(res))
            self.assertIn("same log", row.get("error") or "")

    def test_bundles_spanning_years_are_refused(self):
        write_log(self.log, SESSIONS)
        a = self.make("a.zip")
        b = os.path.join(self.d, "b.zip")
        bundle.make(b, self.log, T0 + timedelta(days=200), T0 + timedelta(days=200, hours=1),
                    claude_projects=self.projects, key_id="apikey_k1")
        with self.assertRaises(ValueError):
            team.run([a, b], None, ledger=self.ledger, org_minutes={}, keys=[], now=NOW + timedelta(days=300))


class EmptyLogAndHugeNumbersTest(Home):
    def test_bundling_an_empty_log_says_so(self):
        open(self.log, "w").close()
        with self.assertRaises(ValueError) as cm:
            self.make("empty.zip")
        self.assertIn("empty", str(cm.exception))

    def test_huge_integers_are_refused_quickly(self):
        with self.assertRaises(ValueError):
            chainlog.loads('{"input_tokens": 1%s}' % ("0" * 100000))
        self.assertEqual(chainlog.loads('{"n": 123}'), {"n": 123})


class SettlingTest(Home):
    def test_no_verified_until_the_last_minutes_can_be_billed(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        end = T0 + timedelta(hours=1)
        early = self.receive_verified(path, now=end + timedelta(minutes=10), record=False)
        self.assertEqual(early["verdict"], "consistent")
        self.assertIn("too recently", bundle.render_receive(early))
        later = self.receive_verified(path, now=end + timedelta(hours=2), record=False)
        self.assertEqual(later["verdict"], "verified")


class FinalReviewTest(Home):
    """The review of the fixes above (Nov 15, afternoon)."""

    def receive_with_bill(self, path, bill, now, **kw):
        from vawr import check
        real = check.run
        check.run = lambda start, end, *a, **k: {
            "window": [start.isoformat(), end.isoformat()], "chain": {"ok": True, "entries": 0, "head": ""},
            "coverage": {"ok": None, "local_requests": 0, "logged_requests_in_window": 0, "token_mismatches": 0,
                         "unlogged_sessions": []},
            "bill": bill, "sessions": {"ok": True, "days": []}, "level": "provider"}
        try:
            return bundle.receive(path, admin_key="x", ledger=self.ledger, now=now, **kw)
        finally:
            check.run = real

    def test_usage_not_billed_yet_while_settling_is_not_a_failure(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        end = T0 + timedelta(hours=1)
        ahead = {"ok": False, "gaps": [], "log_excess": [{"minute": minute(59), "tokens": tok(10)}],
                 "provider_tokens": {"input": 1}, "background_tokens": {"input": 0}}
        early = self.receive_with_bill(path, ahead, end + timedelta(minutes=10), record=False)
        self.assertEqual(early["verdict"], "consistent")
        self.assertIn("not billed yet", bundle.render_receive(early))
        late = self.receive_with_bill(path, ahead, end + timedelta(hours=2), record=False)
        self.assertEqual(late["verdict"], "failed")

    def test_summary_puts_the_verdict_first(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", title="VERIFIED by everyone")
        out = self.receive_verified(path, now=NOW, record=False)
        line = [l for l in bundle.render_receive(out).splitlines() if l.startswith("Summary: ")][0]
        self.assertTrue(line.startswith("Summary: VERIFIED: VERIFIED by everyone"), line)

    def test_team_waits_for_the_last_minutes_too(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", only_projects=["grant"])
        org = {"apikey_k1": {minute(1): {"claude-sonnet-5-5": tok(100)}, minute(2): {"claude-sonnet-5-5": tok(50)},
                             minute(5): {"claude-haiku-5-5": tok(30)}}}
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = team.run([path], None, ledger=self.ledger, org_minutes=org,
                       keys=[{"id": "apikey_k1", "name": "grant key"}], fetch=lambda d: recs,
                       now=T0 + timedelta(hours=1, minutes=10))
        self.assertEqual(res["keys"][0]["status"], "check")
        self.assertIn("less than", res["keys"][0]["note"])

    def test_a_fork_is_recorded_as_failed(self):
        write_log(self.log, SESSIONS)
        honest = self.make("honest.zip", only_projects=["grant"])
        fork = os.path.join(self.d, "fork.jsonl")
        with open(fork, "w") as fh:
            fh.write(chainlog.canonical(next(chainlog.read_entries(self.log))[1]) + "\n")
        log = chainlog.ChainLog(fork)
        for e in [e for _, e in chainlog.read_entries(self.log)][1:]:
            ev = json.loads(json.dumps(e["event"]))
            if "input_tokens" in (ev.get("attributes") or {}):
                ev["attributes"]["input_tokens"] += 1
            log.append(ev)
        forked = self.make("fork.zip", log=fork, only_projects=["grant"])
        team.run([honest, forked], None, ledger=self.ledger, org_minutes={},
                 keys=[{"id": "apikey_k1", "name": "grant key"}], fetch=lambda d: [], now=NOW)
        verdicts = {json.loads(l)["bundle"]: json.loads(l)["verdict"] for l in open(self.ledger) if l.strip()}
        self.assertEqual(verdicts["fork.zip"], "failed")
        self.assertEqual(verdicts["honest.zip"], "failed")  # can't tell which copy is honest: both fail

    def test_explaining_an_http_error_without_a_body(self):
        import urllib.error
        exc = urllib.error.HTTPError("https://api.anthropic.com/x", 400, "Bad Request", {}, None)
        self.assertIn("HTTP 400", usage_api.explain(exc))


if __name__ == "__main__":
    unittest.main()
