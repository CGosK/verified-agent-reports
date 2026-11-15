"""Sessions Claude Code doesn't report to Anthropic (DISABLE_TELEMETRY or
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC set): vawr logs them, Anthropic doesn't count
them (work/results/telemetry_off_*.json). More in the log than Anthropic counted isn't
hidden work, so it doesn't fail, but it keeps a report from VERIFIED and says why."""
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works with `-s tests` and `-s tests -t .`
from test_bundle_team import NOW, SESSIONS, T0, Home, cc_records, iso, write_log  # noqa: E402
from vawr import auditor, bundle, check, configure, daily, team, usage_api

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
        # Anthropic counted a non-interactive session the log lacks; the log's xterm one wasn't counted.
        # The log covers the whole day (it started the day before), so the shortfall can't be outside it.
        early = [("s0", "grant", "non-interactive", [(-400, "claude-sonnet-5-5", 10)])]
        write_log(self.log, early + SESSIONS)
        day0 = T0.replace(hour=0)
        res = daily.check(None, "apikey_k1", day0, day0 + timedelta(days=1), [self.log], only_projects=["grant"],
                          now=NOW, key_name="grant key",
                          fetch=lambda d: cc_records({"non-interactive": (2, {"claude-sonnet-5-5": 250})}))
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
        self.assertIn("Bill checked against Anthropic", bundle.receive_html(out))

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


HONEST_CELLS = {"non-interactive": (1, {"claude-sonnet-5-5": 150}), "xterm-256color": (1, {"claude-haiku-5-5": 30})}


def tok(**kw):
    return dict({"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}, **kw)


def billed(extra_cache_read=0, extra_haiku_input=0, extra_output=0):
    """Anthropic's per-minute bill for the grant project's requests in SESSIONS, plus
    unlogged Haiku usage at minute 5 (where s2 ran)."""
    m = lambda k: iso(T0 + timedelta(minutes=k))  # noqa: E731
    return {m(1): {"claude-sonnet-5-5": tok(input=100)}, m(2): {"claude-sonnet-5-5": tok(input=50)},
            m(5): {"claude-haiku-5-5": tok(input=30 + extra_haiku_input, output=extra_output,
                                           cache_read=extra_cache_read)}}


class EndToEndTest(Home):
    """`vawr receive` with the real bill and sessions checks; only Anthropic's API is stood in."""

    def stub_api(self, minutes, cells, fail_count=False):
        saved = (usage_api.minute_usage_any, usage_api.api_keys, usage_api.claude_code_day)

        def day(admin, d):
            if fail_count:
                raise urllib.error.URLError("offline")
            return cc_records(cells) if d == T0.date().isoformat() else []
        usage_api.minute_usage_any = lambda admin, key, start, end, source="auto": (minutes, "legacy", None)
        usage_api.api_keys = lambda admin: [{"id": "apikey_k1", "name": "grant key"}]
        usage_api.claude_code_day = day

        def restore():
            usage_api.minute_usage_any, usage_api.api_keys, usage_api.claude_code_day = saved
        self.addCleanup(restore)

    def receive(self, sessions, minutes, cells, **kw):
        write_log(self.log, sessions)
        path = self.make("a.zip", only_projects=["grant"])
        self.stub_api(minutes, cells, **kw)
        return bundle.receive(path, admin_key="x", ledger=self.ledger)

    def test_honest_log_is_verified(self):
        out = self.receive(SESSIONS, billed(), HONEST_CELLS)
        self.assertEqual(out["verdict"], "verified", bundle.render_receive(out))

    def test_honest_uncounted_session_is_consistent(self):
        out = self.receive(SESSIONS, billed(), {"non-interactive": (1, {"claude-sonnet-5-5": 150})})
        self.assertEqual(out["verdict"], "consistent")
        self.assertIn("NOTE  sessions", bundle.render_receive(out))

    def test_made_up_sessions_with_no_tokens_buy_no_allowance(self):
        # review finding: 3 fake zero-token sessions beside s2 passed 21,000 unlogged tokens as background
        fakes = [("f%d" % i, "grant", "xterm-256color", [(5, "claude-haiku-5-5", 0)]) for i in range(3)]
        out = self.receive(SESSIONS + fakes, billed(extra_cache_read=21000), HONEST_CELLS)
        self.assertEqual(out["verdict"], "failed")
        self.assertFalse(out["check"]["bill"]["ok"])
        self.assertIs(out["check"]["sessions"]["ok"], False)  # sessions Anthropic never saw, no usage

    def test_made_up_sessions_with_tokens_cant_excuse_more_allowance_than_anthropic_counted(self):
        fakes = [("f%d" % i, "grant", "xterm-256color", [(5, "claude-haiku-5-5", 1)]) for i in range(3)]
        out = self.receive(SESSIONS + fakes, billed(extra_cache_read=21000, extra_haiku_input=3), HONEST_CELLS)
        self.assertTrue(out["check"]["bill"]["ok"])  # the bill check alone gives them allowance...
        self.assertEqual(out["verdict"], "failed")   # ...but Anthropic counted 2 sessions, not 5
        day = out["check"]["sessions"]["days"][0]
        self.assertEqual(day["status"], "fail")
        self.assertGreater(day["background_over_count"]["credited"], day["background_over_count"]["justified"])
        self.assertIn("background allowance", bundle.render_receive(out))

    def test_a_log_that_breaks_the_sessions_check_fails(self):
        real = daily.log_days
        daily.log_days = lambda *a, **k: (_ for _ in ()).throw(KeyError("crafted"))
        self.addCleanup(setattr, daily, "log_days", real)
        out = self.receive(SESSIONS, billed(), HONEST_CELLS)
        self.assertEqual(out["verdict"], "failed")
        self.assertIn("the log made the checks fail", out["provider_error"])

    def test_anthropic_count_unreadable_is_consistent_not_failed(self):
        out = self.receive(SESSIONS, billed(), HONEST_CELLS, fail_count=True)
        self.assertEqual(out["verdict"], "consistent")
        self.assertIn("couldn't read Anthropic's count", out["check"]["sessions"]["error"])


    def test_sessions_the_count_cant_see_buy_no_allowance(self):
        # re-review: 20 made-up sessions, each with 1 Haiku token taken from s2, hidden from the
        # sessions check by a session-level tag (subscription auth, another project) or by a first
        # event two days earlier, passed 199,710 unlogged Haiku tokens as background: VERIFIED
        s2_short = [SESSIONS[0], ("s2", "grant", "xterm-256color", [(5, "claude-haiku-5-5", 10)])]
        # exactly 21 allowances (s2 and the 20) at minute 5: 21 x (1,000 input, 1,500 output, 7,010 cache read)
        bill = billed(extra_haiku_input=21000, extra_output=31500, extra_cache_read=147210)
        for how in ("auth", "project", "earlier"):
            with self.subTest(how=how):
                self.setUp()
                fakes = [("f%d" % i, "grant", "xterm-256color",
                          ([(-2880, "claude-haiku-5-5", 0)] if how == "earlier" else []) +
                          [(5, "claude-haiku-5-5", 1)]) for i in range(20)]
                write_log(self.log, s2_short)
                extra = {"auth": {"auth": "account"}, "project": {"project": "other-client"}}.get(how)
                if extra:
                    write_log(self.log, fakes, extra_attrs=extra)  # tags only the session's first event
                else:
                    write_log(self.log, fakes)
                path = self.make("a.zip", only_projects=["grant"])
                self.stub_api(bill, HONEST_CELLS)
                out = bundle.receive(path, admin_key="x", ledger=self.ledger)
                self.assertEqual(out["verdict"], "failed", bundle.render_receive(out))
                self.tearDown()


DAY0 = datetime(2026, 11, 13, tzinfo=timezone.utc)


class SessionsRulesTest(unittest.TestCase):
    def anth(self, cells):
        return daily.anthropic_days(None, ["2026-11-13"], {"api_key_name": "grant key"},
                                    fetch=lambda d: cc_records(cells))

    def logd(self, sessions):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.jsonl")
            write_log(p, sessions)
            return daily.log_days([p], ["2026-11-13"])[0]

    def test_year_one_timestamp_is_no_time_not_a_crash(self):
        self.assertIsNone(daily._parse("0001-01-01T00:00:00+01:00"))

    def test_a_log_that_ends_mid_day_makes_a_shortfall_partial_not_failed(self):
        anth = self.anth({"non-interactive": (3, {"claude-sonnet-5-5": 400}),
                          "xterm-256color": (1, {"claude-haiku-5-5": 30})})  # 2 sessions after the log ended
        logd = self.logd(SESSIONS[:2])
        start, end = DAY0.isoformat(), (DAY0 + timedelta(hours=7)).isoformat()
        row = daily.compare(anth, logd, NOW, [start], [end])[0]
        self.assertEqual(row["status"], "partial")
        res = daily.summarize({"days": [row]})
        self.assertIsNone(res["ok"])
        self.assertIn("partway through 2026-11-13", daily.unconfirmed_text(res))
        self.assertEqual(daily.compare(anth, logd, NOW, [start], [(DAY0 + timedelta(days=1)).isoformat()])[0]
                         ["status"], "fail")

    def test_a_whole_day_window_still_fails_a_session_hidden_after_the_last_logged_event(self):
        # the log started the day before; its last event is at 06:08, but the window runs to midnight
        early = [("s0", "grant", "non-interactive", [(-400, "claude-sonnet-5-5", 10)])]
        cells = {"non-interactive": (2, {"claude-sonnet-5-5": 150 + 500}),
                 "xterm-256color": (1, {"claude-haiku-5-5": 30})}  # one more session at 20:00, not logged
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.jsonl")
            write_log(p, early + SESSIONS[:2])

            def run(end):
                return daily.check(None, "apikey_k1", DAY0, end, [p], now=NOW, key_name="grant key",
                                   fetch=lambda day: cc_records(cells) if day == "2026-11-13" else [])
            self.assertEqual(run(DAY0 + timedelta(days=1))["days"][0]["status"], "fail")
            self.assertEqual(run(DAY0 + timedelta(hours=7))["days"][0]["status"], "partial")

    def test_background_is_grouped_by_utc_day_whatever_the_offset(self):
        # re-review: minutes keyed with a -05:00 offset were grouped by their local date
        sess = daily.summarize({"days": [
            dict(day="2026-11-13", status="pass", anthropic_sessions=1, log_sessions=1, token_difference={}),
            dict(day="2026-11-14", status="pass", anthropic_sessions=0, log_sessions=0, token_difference={})]})
        bill = {"per_minute": {"2026-11-13T23:30:00-05:00": {"background": 7010}}}  # 04:30 UTC on the 14th
        daily.limit_background(sess, bill, now=NOW)
        self.assertEqual([r["status"] for r in sess["days"]], ["pass", "fail"])
        from vawr import billcheck
        self.assertEqual(billcheck.parse_when("2026-11-13T23:30-05:00").utcoffset(), timedelta(0))

    def test_the_cap_leaves_out_minutes_anthropic_hasnt_counted_yet(self):
        # re-review: received at 07:10, Anthropic hadn't counted s2 (06:50) yet: a false FAILED
        sess = daily.summarize({"days": [dict(day="2026-11-13", status="pending", anthropic_sessions=1,
                                              log_sessions=2, token_difference={})]})
        bill = {"per_minute": {"2026-11-13T06:01:00+00:00": {"background": 7010},
                               "2026-11-13T06:50:00+00:00": {"background": 7010}}}
        daily.limit_background(sess, bill, now=datetime(2026, 11, 13, 7, 10, tzinfo=timezone.utc))
        self.assertEqual(sess["days"][0]["status"], "pending")
        daily.limit_background(sess, bill, now=NOW)  # a week later both count, and 1 session justifies one
        self.assertEqual(sess["days"][0]["status"], "fail")

    def test_a_partial_day_with_both_a_shortfall_and_an_excess_is_partial(self):
        # re-review: work after the bundle (shortfall) beside a telemetry-off session (excess)
        self.assertEqual(daily._status(1, {"m": 400}, 2, {"m": 180}, True, True)[0], "partial")
        self.assertEqual(daily._status(1, {"m": 400}, 2, {"m": 180}, True, False)[0], "fail")

    def test_a_day_with_logged_requests_is_never_before_the_log(self):
        # re-review: requests without a session ID on day D left the log "starting" on D+1
        from vawr import chainlog
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "log.jsonl")
            log = chainlog.ChainLog(p)
            log.append({"name": "api_request", "time": iso(T0), "attributes": {
                "project": "grant", "auth": "api_key", "model": "claude-sonnet-5-5", "input_tokens": 500,
                "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0,
                "event.timestamp": iso(T0)}})
            write_log(p, [("s9", "grant", "non-interactive", [(24 * 60, "claude-sonnet-5-5", 100)])])
            res = daily.check(None, "apikey_k1", DAY0, DAY0 + timedelta(days=2), [p], now=NOW, key_name="grant key",
                              fetch=lambda day: cc_records({"non-interactive": (1 if day > "2026-11-13" else 2, {
                                  "claude-sonnet-5-5": 100 if day > "2026-11-13" else 500})}))
            self.assertNotEqual(res["days"][0]["status"], "before_log")
            self.assertIsNot(res["ok"], True)

    def test_pending_and_partial_days_are_never_confirmed(self):
        for st in ("pending", "partial", "uncounted"):
            self.assertIsNone(daily.overall([{"status": "pass"}, {"status": st}]), st)

    def test_extra_sessions_without_tokens_fail(self):
        self.assertEqual(daily._status(1, {"m": 10}, 3, {"m": 10}, True, False)[0], "fail")
        self.assertEqual(daily._status(1, {"m": 10}, 2, {"m": 15}, True, False)[0], "uncounted")
        self.assertEqual(daily._status(1, {"m": 10}, 2, {"m": 15}, False, False)[0], "pending")

    def test_a_session_without_a_terminal_type_is_still_compared_per_terminal(self):
        # review finding: one terminal-less session switched the per-terminal check off, so a hidden
        # non-interactive session could be offset by a session elsewhere
        anth = self.anth({"non-interactive": (2, {"claude-sonnet-5-5": 150, "claude-haiku-5-5": 30})})
        logd = self.logd([SESSIONS[0], ("s2", "grant", None, [(5, "claude-haiku-5-5", 30)])])
        row = daily.compare(anth, logd, NOW, [DAY0.isoformat()])[0]
        self.assertEqual({c["terminal"]: c["status"] for c in row["by_terminal"]},
                         {"non-interactive": "fail", "unknown": "uncounted"})
        self.assertEqual(row["status"], "fail")

    def test_requests_without_a_session_get_no_background_allowance(self):
        t = T0 + timedelta(minutes=3)
        reqs = [{"mode": "api_key", "time": iso(t), "model": "claude-haiku-5-5", "tokens": tok(input=0),
                 "session_id": None, "run_id": None, "request_id": "r%d" % i} for i in range(3)]
        pm = {t.replace(second=0): {"claude-haiku-5-5": tok(cache_read=7000)}}
        res = auditor.check_provider(reqs, T0, T0 + timedelta(hours=1), key_mode="api_key", provider_minutes=pm)
        self.assertFalse(res["ok"])
        self.assertEqual(sum(res["background_tokens"].values()), 0)

    def test_level_and_note_for_unconfirmed_days(self):
        sess = daily.summarize({"days": [{"day": "2026-11-13", "status": "partial", "anthropic_sessions": 2,
                                          "log_sessions": 1, "token_difference": {}, "by_terminal": []}]})
        res = {"window": [iso(T0), iso(T0 + timedelta(hours=1))], "chain": {"ok": True, "entries": 1, "head": "h"},
               "coverage": {"ok": None, "local_requests": 0, "logged_requests_in_window": 0, "token_mismatches": 0,
                            "unlogged_sessions": []},
               "bill": {"ok": True, "gaps": [], "log_excess": [], "provider_tokens": {"input": 1},
                        "background_tokens": {"input": 0}}, "sessions": sess}
        self.assertEqual(check.level(res), "provider-unconfirmed")
        text = check.render(res)
        self.assertIn("NOTE  sessions", text)
        self.assertIn("couldn't confirm every day", text)


class TeamWindowTest(Home):
    def test_team_doesnt_pass_a_period_that_hasnt_ended(self):
        write_log(self.log, SESSIONS)
        path = os.path.join(self.d, "open.zip")
        bundle.make(path, self.log, T0, T0 + timedelta(days=14), claude_projects=self.projects, key_id="apikey_k1",
                    only_projects=["grant"])
        minute = lambda m: iso(T0 + timedelta(minutes=m))  # noqa: E731
        org = {"apikey_k1": {minute(1): {"claude-sonnet-5-5": tok(input=100)},
                             minute(2): {"claude-sonnet-5-5": tok(input=50)},
                             minute(5): {"claude-haiku-5-5": tok(input=30)}}}
        res = team.run([path], None, ledger=self.ledger, org_minutes=org,
                       keys=[{"id": "apikey_k1", "name": "grant key"}],
                       fetch=lambda d: cc_records(HONEST_CELLS) if d == "2026-11-13" else [],
                       now=T0 + timedelta(hours=3))
        row = res["keys"][0]
        self.assertEqual(row["status"], "check")
        self.assertIn("hasn't ended", row["note"])

    def test_level_when_the_count_couldnt_be_read(self):
        res = {"chain": {"ok": True}, "coverage": {"ok": None}, "bill": {"gaps": [], "log_excess": []},
               "sessions": {"ok": None, "error": "couldn't read Anthropic's count"}}
        self.assertEqual(check.level(res), "provider-unconfirmed")


class BadTimeTest(unittest.TestCase):
    def test_a_bad_since_is_a_usage_message_not_a_traceback(self):
        import contextlib
        import io
        from vawr.__main__ import main
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["billcheck", "--since", "2026-11-15T08:43 08:46"]), 2)
        self.assertIn("isn't a time vawr reads", err.getvalue())


class TelemetryOffSettingsTest(unittest.TestCase):
    def test_shell_user_project_and_managed_settings(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "settings.json")
            with open(p, "w") as fh:
                json.dump({"env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "0"}}, fh)
            proj = os.path.join(d, "proj")
            os.makedirs(os.path.join(proj, ".claude"))
            local = os.path.join(proj, ".claude", "settings.local.json")
            with open(local, "w") as fh:
                json.dump({"env": {"DISABLE_TELEMETRY": "1"}}, fh)
            managed = os.path.join(d, "managed.json")
            with open(managed, "w") as fh:
                json.dump({"env": {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "yes"}}, fh)
            found = configure.telemetry_off_settings({"DISABLE_TELEMETRY": "true"}, p, proj, [managed])
            self.assertEqual(found, [
                "DISABLE_TELEMETRY in the shell",
                'DISABLE_TELEMETRY="0" in %s' % p,  # we only tested "1"; a warning on "0" costs little
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC in %s" % p,
                "DISABLE_TELEMETRY in %s" % local,
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="yes" in %s' % managed])
            empty = os.path.join(d, "empty")
            os.makedirs(empty)
            self.assertEqual(configure.telemetry_off_settings({"DISABLE_TELEMETRY": " "}, os.path.join(d, "no.json"),
                                                              empty, []), [])
            self.assertIn("CONSISTENT", configure.telemetry_off_warning({}, p, empty, []))
            self.assertEqual(configure.telemetry_off_warning({}, os.path.join(d, "no.json"), empty, []), "")

    def test_odd_settings_files_dont_crash(self):
        with tempfile.TemporaryDirectory() as d:
            for i, body in enumerate(['[1, 2]', '"x"', 'null', '{"env": [1]}', '{bad', '\x00\x01']):
                p = os.path.join(d, "s%d.json" % i)
                with open(p, "w") as fh:
                    fh.write(body)
                self.assertEqual(configure.telemetry_off_settings({}, p, d, []), [])


class WindowTextTest(unittest.TestCase):
    def test_end_on_another_day_shows_its_date(self):
        from vawr.billcheck import window_text
        self.assertEqual(window_text(("2026-11-14T00:00:00+00:00", "2026-11-15T00:00:00+00:00")),
                         "2026-11-14 00:00 to 2026-11-15 00:00")
        self.assertEqual(window_text(("2026-11-14T00:00:00+00:00", "2026-11-14T07:56:00+00:00")),
                         "2026-11-14 00:00 to 07:56")


if __name__ == "__main__":
    unittest.main()

