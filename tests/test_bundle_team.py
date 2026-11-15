"""Bundles, payer receive, continuity, the sessions check and team mode, offline:
Anthropic's records are passed in, never fetched."""
import json
import os
import tempfile
import unittest
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone

from vawr import bundle, chainlog, check, daily, html_report, team, validate

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)  # every test day is long over


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def write_log(path, sessions, extra_attrs=None):
    """sessions: [(session_id, project, terminal, [(minute_offset, model, tokens), ...])]"""
    log = chainlog.ChainLog(path)
    for sid, project, terminal, reqs in sessions:
        base = {"session.id": sid, "project": project, "category": "safety", "auth": "api_key",
                "terminal.type": terminal, "anthropic.provider": "firstParty"}
        log.append({"name": "user_prompt", "time": iso(T0 + timedelta(minutes=reqs[0][0])),
                    "attributes": dict(base, prompt="<REDACTED>", **(extra_attrs or {}))})
        for i, (m, model, n) in enumerate(reqs):
            log.append({"name": "api_request", "time": iso(T0 + timedelta(minutes=m)), "attributes": dict(
                base, request_id="%s-r%d" % (sid, i), model=model, input_tokens=n, output_tokens=0,
                cache_read_tokens=0, cache_creation_tokens=0, cost_usd=0.01,
                **{"event.timestamp": iso(T0 + timedelta(minutes=m, seconds=5))})})


SESSIONS = [("s1", "grant", "non-interactive", [(1, "claude-sonnet-5-5", 100), (2, "claude-sonnet-5-5", 50)]),
            ("s2", "grant", "xterm-256color", [(5, "claude-haiku-5-5", 30)]),
            ("s3", "other-client", "non-interactive", [(8, "claude-sonnet-5-5", 70)])]


def cc_records(day_sessions):
    """Claude Code analytics records from {terminal: (sessions, {model: tokens})}."""
    return [{"actor": {"type": "api_actor", "api_key_name": "grant key"}, "terminal_type": term,
             "core_metrics": {"num_sessions": n, "lines_of_code": {"added": 3, "removed": 1},
                              "commits_by_claude_code": 1, "pull_requests_by_claude_code": 0},
             "model_breakdown": [{"model": m, "tokens": {"input": t, "output": 0, "cache_read": 0,
                                                          "cache_creation": 0}} for m, t in models.items()]}
            for term, (n, models) in day_sessions.items()]


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.log = os.path.join(self.d, "events.jsonl")
        self.projects = os.path.join(self.d, "claude-projects")
        os.makedirs(self.projects)
        self.ledger = os.path.join(self.d, "received.jsonl")
        self._sent = bundle.SENT
        bundle.SENT = os.path.join(self.d, "sent.jsonl")

    def tearDown(self):
        bundle.SENT = self._sent
        self.tmp.cleanup()

    def receive_verified(self, path, **kw):
        """receive with a stand-in for the payer's Admin-key checks: the bill matched."""
        real = check.run
        check.run = lambda start, end, *a, **k: {
            "window": [start.isoformat(), end.isoformat()], "chain": {"ok": True, "entries": 0, "head": ""},
            "coverage": {"ok": None, "local_requests": 0, "logged_requests_in_window": 0, "token_mismatches": 0,
                         "unlogged_sessions": []},
            "bill": {"ok": True, "gaps": [], "log_excess": [], "provider_tokens": {"input": 1},
                     "background_tokens": {"input": 0}},
            "sessions": {"ok": True, "days": []}, "level": "provider"}
        try:
            return bundle.receive(path, admin_key="x", ledger=self.ledger, **kw)
        finally:
            check.run = real

    def make(self, name, log=None, **kw):
        out = os.path.join(self.d, name)
        kw.setdefault("key_id", "apikey_k1")
        bundle.make(out, log or self.log, T0, T0 + timedelta(hours=1), claude_projects=self.projects, **kw)
        return out


class SessionsCheckTest(unittest.TestCase):
    def day(self, cells, log_cells, starts=(), now=NOW):
        a = {"2026-11-13": {"sessions": sum(c[0] for c in cells.values()),
                            "tokens": sum((Counter(c[1]) for c in cells.values()), Counter()),
                            "cells": {t: {"sessions": c[0], "tokens": Counter(c[1])} for t, c in cells.items()},
                            "work": Counter()}}
        lg = {"2026-11-13": {"sessions": set().union(*[c[0] for c in log_cells.values()]) if log_cells else set(),
                             "tokens": sum((Counter(c[1]) for c in log_cells.values()), Counter()),
                             "cells": {t: {"sessions": c[0], "tokens": Counter(c[1])} for t, c in log_cells.items()}}}
        return daily.compare(a, lg, now, starts)[0]

    def test_equal_counts_pass(self):
        r = self.day({"x": (2, {"m": 10})}, {"x": ({"a", "b"}, {"m": 10})})
        self.assertEqual(r["status"], "pass")

    def test_missing_session_fails_even_with_equal_day_tokens_elsewhere(self):
        r = self.day({"x": (2, {"m": 10}), "y": (1, {"m": 5})}, {"x": ({"a", "b"}, {"m": 10})})
        self.assertEqual(r["status"], "fail")
        self.assertEqual([c["status"] for c in r["by_terminal"]], ["pass", "fail"])

    def test_log_started_that_day_does_not_fail_on_shortfall(self):
        r = self.day({"x": (3, {"m": 10})}, {"x": ({"a"}, {"m": 4})}, starts=["2026-11-13T12:00:00Z"])
        self.assertEqual(r["status"], "partial")

    def test_day_before_the_log_is_not_checked(self):
        r = self.day({"x": (3, {"m": 10})}, {}, starts=["2026-11-14T01:00:00Z"])
        self.assertEqual(r["status"], "before_log")

    def test_log_excess_waits_until_the_day_is_over(self):
        early = datetime(2026, 11, 13, 20, tzinfo=timezone.utc)
        self.assertEqual(self.day({"x": (1, {"m": 5})}, {"x": ({"a", "b"}, {"m": 10})}, now=early)["status"],
                         "pending")
        self.assertEqual(self.day({"x": (1, {"m": 5})}, {"x": ({"a", "b"}, {"m": 10})})["status"], "fail")

    def test_overall(self):
        self.assertIsNone(daily.overall([{"status": "partial"}, {"status": "before_log"}]))
        self.assertTrue(daily.overall([{"status": "pass_so_far"}, {"status": "partial"}]))
        self.assertFalse(daily.overall([{"status": "pass"}, {"status": "fail"}]))


class SessionsOnLogTest(Home):
    def test_log_side_and_anthropic_side_match(self):
        write_log(self.log, SESSIONS)
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = daily.check(None, "apikey_k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"], now=NOW,
                          key_name="grant key", fetch=lambda d: recs)
        self.assertEqual(res["days"][0]["status"], "pass")  # equal counts pass even on the log's first day
        self.assertEqual([c["status"] for c in res["days"][0]["by_terminal"]], ["pass", "pass"])
        self.assertEqual(res["days"][0]["work"]["commits"], 2)

    def test_hidden_session_fails_its_terminal(self):
        write_log(self.log, SESSIONS)
        recs = cc_records({"non-interactive": (2, {"claude-sonnet-5-5": 190}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = daily.check(None, "apikey_k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"], now=NOW,
                          key_name="grant key", fetch=lambda d: recs)
        cells = {c["terminal"]: c for c in res["days"][0]["by_terminal"]}
        self.assertEqual(cells["non-interactive"]["token_difference"], {"claude-sonnet-5-5": 40})


class BundleTest(Home):
    def test_round_trip_without_admin_key_is_consistent(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", only_projects=["grant"], title="Grant X")
        with zipfile.ZipFile(path) as z:
            self.assertEqual(sorted(z.namelist()), sorted(bundle.MEMBERS))
            m = json.loads(z.read("bundle.json"))
        self.assertEqual(m["only_projects"], ["grant"])
        self.assertEqual(m["level"], "tamper-evident")
        out = bundle.receive(path, ledger=self.ledger)
        self.assertEqual(out["verdict"], "consistent")
        self.assertTrue(out["report"]["ok"])
        self.assertIsNone(out["continuity"]["ok"])
        cats = {c["category"]: c["total_tokens"] for c in out["rebuilt_report"]["categories"]}
        self.assertEqual(cats, {"safety": 180})  # the other client's 70 tokens are left out
        page = bundle.receive_html(out)
        self.assertIn("Tamper-evident only", page)
        self.assertIn("Continuity", page)

    def test_edited_report_fails(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        edited = os.path.join(self.d, "edited.zip")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(edited, "w") as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == "report.json":
                    rep = json.loads(data)
                    rep["categories"][0]["tokens"]["input"] += 1000
                    data = json.dumps(rep)
                dst.writestr(name, data)
        self.assertEqual(bundle.receive(edited, ledger=self.ledger)["verdict"], "failed")

    def test_next_report_continues_and_rebuild_is_caught(self):
        write_log(self.log, SESSIONS[:2])
        first = self.make("first.zip")
        self.assertEqual(bundle.receive(first, ledger=self.ledger)["verdict"], "consistent")
        write_log(self.log, SESSIONS[2:])  # more work, same log
        second = self.make("second.zip")
        with zipfile.ZipFile(second) as z:
            self.assertEqual(json.loads(z.read("bundle.json"))["previous_head"],
                             json.loads(zipfile.ZipFile(first).read("bundle.json"))["log"]["head"])
        out = bundle.receive(second, ledger=self.ledger)
        self.assertTrue(out["continuity"]["ok"])
        # relabel an early entry and rebuild the chain: the first report's head disappears
        entries = [e for _, e in chainlog.read_entries(self.log)]
        entries[1]["event"]["attributes"]["category"] = "capabilities"
        validate.rehash(entries)
        rebuilt = os.path.join(self.d, "rebuilt.jsonl")
        with open(rebuilt, "w") as fh:
            for e in entries:
                fh.write(chainlog.canonical(e) + "\n")
        third = self.make("third.zip", log=rebuilt)
        out = bundle.receive(third, ledger=self.ledger)
        self.assertIs(out["continuity"]["ok"], False)
        self.assertEqual(out["verdict"], "failed")

    def test_log_rebuilt_from_first_entry_is_a_new_log_and_fails_for_the_same_key(self):
        write_log(self.log, SESSIONS)
        self.assertEqual(self.receive_verified(self.make("first.zip"))["verdict"], "verified")
        entries = [e for _, e in chainlog.read_entries(self.log)]
        entries[0]["event"]["attributes"]["category"] = "capabilities"
        validate.rehash(entries)
        rebuilt = os.path.join(self.d, "rebuilt.jsonl")
        with open(rebuilt, "w") as fh:
            for e in entries:
                fh.write(chainlog.canonical(e) + "\n")
        out = bundle.receive(self.make("again.zip", log=rebuilt), ledger=self.ledger)
        self.assertIs(out["continuity"]["ok"], False)

    def test_refuses_logs_with_prompt_text(self):
        write_log(self.log, SESSIONS[:1], extra_attrs={"prompt_text": "secret plan"})
        with self.assertRaises(ValueError):
            self.make("a.zip")
        self.make("b.zip", allow_text=True)

    def test_zip_paths_are_never_used(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        evil = os.path.join(self.d, "evil.zip")
        with zipfile.ZipFile(path) as src, zipfile.ZipFile(evil, "w") as dst:
            for name in src.namelist():
                dst.writestr(name, src.read(name))
            dst.writestr("../escaped.txt", "x")
        work = os.path.join(self.d, "work")
        os.makedirs(work)
        bundle.receive(evil, ledger=self.ledger, workdir=work)
        self.assertFalse(os.path.exists(os.path.join(self.d, "escaped.txt")))
        self.assertEqual(sorted(os.listdir(work)), sorted(bundle.MEMBERS))

    def test_not_a_bundle(self):
        junk = os.path.join(self.d, "junk.zip")
        with zipfile.ZipFile(junk, "w") as z:
            z.writestr("hello.txt", "hi")
        with self.assertRaises(ValueError):
            bundle.receive(junk, ledger=self.ledger)


class TeamTest(Home):
    def test_unreported_key_and_matched_key(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", only_projects=["grant"])
        minute = lambda m: iso(T0 + timedelta(minutes=m))  # noqa: E731
        tok = lambda n: {"input": n, "output": 0, "cache_read": 0, "cache_creation": 0}  # noqa: E731
        org = {"apikey_k1": {minute(1): {"claude-sonnet-5-5": tok(100)}, minute(2): {"claude-sonnet-5-5": tok(50)},
                      minute(5): {"claude-haiku-5-5": tok(30)}},
               "apikey_k2": {minute(9): {"claude-opus-5-5": tok(500)}}}
        keys = [{"id": "apikey_k1", "name": "grant key"}, {"id": "apikey_k2", "name": "intern key"}]
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = team.run([path], None, ledger=self.ledger, org_minutes=org, keys=keys, fetch=lambda d: recs, now=NOW)
        by = {r["key_id"]: r for r in res["keys"]}
        self.assertEqual(by["apikey_k1"]["status"], "pass")
        self.assertEqual(by["apikey_k2"]["status"], "no report")
        self.assertEqual(res["billed_tokens"], 680)
        self.assertEqual(res["accounted_tokens"], 180)
        self.assertIn("NO REPORT", team.render(res))


class LevelAndHtmlTest(unittest.TestCase):
    def base(self, **kw):
        res = {"chain": {"ok": True}, "coverage": {"ok": None}, "bill": None, "sessions": None}
        res.update(kw)
        return res

    def test_levels(self):
        self.assertEqual(check.level(self.base()), "tamper-evident")
        self.assertEqual(check.level(self.base(bill={"gaps": []})), "provider")
        self.assertEqual(check.level(self.base(bill={"gaps": [{}]})), "failed")
        self.assertEqual(check.level(self.base(bill={"gaps": []}, sessions={"ok": False})), "failed")

    def test_html_shows_level_split_and_sessions(self):
        rep = {"log": {"entries": 3, "head": "ab" * 32, "chain_ok": True}, "categories": [],
               "billing": {"api_key": 75, "subscription": 25, "unknown": 0}}
        chk = self.base(level="provider", sessions={"ok": True, "days": [
            {"day": "2026-11-13", "status": "pass", "anthropic_sessions": 2, "log_sessions": 2,
             "token_difference": {}, "work": {"commits": 1}}]})
        page = html_report.render(rep, check=chk)
        self.assertIn("Checked against Anthropic", page)
        self.assertIn("75.0% on an API key", page)
        self.assertIn("equal Anthropic", page)


if __name__ == "__main__":
    unittest.main()


def rewrite(src, dst, change):
    """Copy a bundle, passing each member's bytes through change(name, data)."""
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as b:
        for name in a.namelist():
            b.writestr(name, change(name, a.read(name)))
    return dst


def edit_json(name_wanted, fn):
    def change(name, data):
        if name != name_wanted:
            return data
        obj = json.loads(data)
        fn(obj)
        return json.dumps(obj)
    return change


class ReviewRegressionTest(Home):
    """One test per problem the independent review found."""

    def test_narrower_report_window_fails(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        bad = rewrite(path, os.path.join(self.d, "narrow.zip"), edit_json(
            "report.json", lambda r: r.update(window=[iso(T0), iso(T0 + timedelta(minutes=3))])))
        out = bundle.receive(bad, ledger=self.ledger)
        self.assertEqual(out["verdict"], "failed")
        self.assertIn("window", out["report"]["note"])

    def test_report_from_an_earlier_head_fails(self):
        write_log(self.log, SESSIONS)
        early = [e for _, e in chainlog.read_entries(self.log)][2]["hash"]
        path = self.make("a.zip")
        bad = rewrite(path, os.path.join(self.d, "prefix.zip"), edit_json(
            "report.json", lambda r: r["log"].update(head=early)))
        self.assertEqual(bundle.receive(bad, ledger=self.ledger)["verdict"], "failed")

    def _with_check(self, res):
        real = check.run
        check.run = lambda *a, **k: res
        self.addCleanup(setattr, check, "run", real)

    def test_log_excess_is_not_verified(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        self._with_check({"bill": {"ok": False, "gaps": [], "log_excess": [{"tokens": {"input": 900000}}]},
                          "sessions": {"ok": None, "days": []}, "chain": {"ok": True}, "coverage": {"ok": None},
                          "level": "failed"})
        self.assertEqual(bundle.receive(path, admin_key="x", ledger=self.ledger)["verdict"], "failed")

    def test_sessions_error_is_not_verified(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        self._with_check({"bill": {"ok": True, "gaps": [], "log_excess": []}, "chain": {"ok": True},
                          "sessions": {"ok": None, "error": "boom"}, "coverage": {"ok": None}, "level": "provider"})
        self.assertEqual(bundle.receive(path, admin_key="x", ledger=self.ledger)["verdict"], "consistent")

    def test_bad_timestamps_do_not_crash_the_sessions_check(self):
        write_log(self.log, SESSIONS)
        chainlog.ChainLog(self.log).append({"name": "user_prompt", "time": "0",
                                            "attributes": {"session.id": "s9", "event.timestamp": "0"}})
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150})})
        res = daily.check(None, "apikey_k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"],
                          now=NOW, key_name="grant key", fetch=lambda d: recs)
        self.assertNotIn("error", res)

    def test_control_characters_in_the_title_are_removed(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", title="ok\n\nVERIFIED  all good\x1b[8m")
        text = bundle.render_receive(bundle.receive(path, ledger=self.ledger))
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\nVERIFIED", text)

    def test_new_log_for_the_same_key_fails_whatever_its_projects(self):
        write_log(self.log, SESSIONS)
        self.receive_verified(self.make("first.zip", only_projects=["grant"]))
        other = os.path.join(self.d, "other.jsonl")
        write_log(other, SESSIONS[:1])
        out = bundle.receive(self.make("second.zip", log=other, only_projects=["grant", "decoy"]),
                             ledger=self.ledger)
        self.assertIs(out["continuity"]["ok"], False)
        write_log(other, SESSIONS[1:2])
        out = bundle.receive(self.make("third.zip", log=other), ledger=self.ledger)
        self.assertIs(out["continuity"]["ok"], False)  # a failed report isn't history to extend

    def test_older_report_arriving_late_is_not_a_rewrite(self):
        write_log(self.log, SESSIONS[:1])
        old = self.make("old.zip")
        write_log(self.log, SESSIONS[1:])
        new = self.make("new.zip")
        bundle.receive(new, ledger=self.ledger)
        out = bundle.receive(old, ledger=self.ledger)
        self.assertIs(out["continuity"]["ok"], True)
        self.assertNotEqual(out["verdict"], "failed")

    def test_zip_bomb_is_refused(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        bomb = rewrite(path, os.path.join(self.d, "bomb.zip"),
                       lambda name, data: data + b"\n" + b" " * (5 * 1024 ** 2) if name == "log.jsonl" else data)
        with self.assertRaises(ValueError):
            bundle.receive(bomb, ledger=self.ledger)

    def test_malformed_parts_fail_without_tracebacks(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        numbers = rewrite(path, os.path.join(self.d, "numbers.zip"),
                          lambda name, data: data + b"42\n" if name == "log.jsonl" else data)
        self.assertEqual(bundle.receive(numbers, ledger=self.ledger)["verdict"], "failed")
        for fn in (lambda m: m.update(window=[1, 2]), lambda m: m.update(only_projects="grant"),
                   lambda m: m.update(key_id="../../x"), lambda m: m.pop("log")):
            bad = rewrite(path, os.path.join(self.d, "m.zip"), edit_json("bundle.json", fn))
            with self.assertRaises(ValueError):
                bundle.receive(bad, ledger=self.ledger)
        listy = rewrite(path, os.path.join(self.d, "listy.zip"),
                        lambda name, data: b"[]" if name == "report.json" else data)
        self.assertEqual(bundle.receive(listy, ledger=self.ledger)["verdict"], "failed")

    def test_other_projects_line_comes_from_the_log(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", only_projects=["grant"])
        bad = rewrite(path, os.path.join(self.d, "hide.zip"), edit_json(
            "bundle.json", lambda m: m.update(log_contents=[])))
        self.assertIn("other projects", bundle.render_receive(bundle.receive(bad, ledger=self.ledger)))


class TeamRegressionTest(Home):
    minute = staticmethod(lambda m: iso(T0 + timedelta(minutes=m)))
    tok = staticmethod(lambda n: {"input": n, "output": 0, "cache_read": 0, "cache_creation": 0})

    def test_two_bundles_from_one_log_are_not_double_counted(self):
        write_log(self.log, SESSIONS)
        a = os.path.join(self.d, "a.zip")
        b = os.path.join(self.d, "b.zip")
        bundle.make(a, self.log, T0, T0 + timedelta(minutes=4), claude_projects=self.projects, key_id="apikey_k1",
                    only_projects=["grant"])
        bundle.make(b, self.log, T0 + timedelta(minutes=4), T0 + timedelta(hours=1), claude_projects=self.projects,
                    key_id="apikey_k1", only_projects=["grant"])
        org = {"apikey_k1": {self.minute(1): {"claude-sonnet-5-5": self.tok(100)},
                             self.minute(2): {"claude-sonnet-5-5": self.tok(50)},
                             self.minute(5): {"claude-haiku-5-5": self.tok(30)}}}
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = team.run([a, b], None, ledger=self.ledger, org_minutes=org, keys=[{"id": "apikey_k1", "name": "grant key"}],
                       fetch=lambda d: recs, now=NOW)
        self.assertEqual(res["keys"][0]["status"], "pass", team.render(res))

    def test_unreadable_bundle_and_key_outside_the_org(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip", key_id="apikey_elsewhere")
        junk = os.path.join(self.d, "junk.zip")
        with open(junk, "wb") as fh:
            fh.write(b"not a zip")
        res = team.run([path, junk], None, ledger=self.ledger, org_minutes={}, keys=[{"id": "apikey_k1", "name": "x"}],
                       fetch=lambda d: [], now=NOW)
        self.assertEqual(len(res["unreadable"]), 1)
        self.assertEqual(res["keys"][0]["status"], "fail")


class SecondReviewTest(Home):
    """The second security review's attacks."""

    def rebuilt(self, change, drop_last=False):
        entries = [e for _, e in chainlog.read_entries(self.log)]
        change(entries)
        if drop_last:
            entries = entries[:-1]
        validate.rehash(entries)
        path = os.path.join(self.d, "rebuilt-%d.jsonl" % len(os.listdir(self.d)))
        with open(path, "w") as fh:
            for e in entries:
                fh.write(chainlog.canonical(e) + "\n")
        return path

    def test_truncated_rewrite_is_caught(self):
        write_log(self.log, SESSIONS)
        self.receive_verified(self.make("first.zip"))
        def relabel(es):
            es[2]["event"]["attributes"]["category"] = "capabilities"
        out = self.receive_verified(self.make("shorter.zip", log=self.rebuilt(relabel, drop_last=True)))
        self.assertIs(out["continuity"]["ok"], False)
        self.assertEqual(out["verdict"], "failed")

    def test_laundering_through_a_keyless_receive_is_caught(self):
        write_log(self.log, SESSIONS)
        self.receive_verified(self.make("first.zip"))
        def relabel(es):
            es[0]["event"]["attributes"]["category"] = "capabilities"
        path = self.rebuilt(relabel)
        bundle.receive(self.make("keyless.zip", log=path, key_id=None), ledger=self.ledger)
        out = self.receive_verified(self.make("again.zip", log=path))
        self.assertIs(out["continuity"]["ok"], False)

    def test_naming_a_key_without_verification_does_not_poison_the_ledger(self):
        other = os.path.join(self.d, "other.jsonl")
        write_log(other, SESSIONS[:1])
        bundle.receive(self.make("decoy.zip", log=other), ledger=self.ledger)  # names apikey_k1, not verified
        write_log(self.log, SESSIONS)
        out = self.receive_verified(self.make("honest.zip"))
        self.assertEqual(out["verdict"], "verified")

    def test_negative_tokens_fail(self):
        write_log(self.log, SESSIONS)
        path = self.make("good.zip")
        chainlog.ChainLog(self.log).append({"name": "api_request", "time": iso(T0 + timedelta(minutes=9)),
                                            "attributes": {"session.id": "s9", "project": "grant", "auth": "api_key",
                                                           "category": "capabilities", "request_id": "s9-r0",
                                                           "model": "claude-sonnet-5-5", "input_tokens": -900000}})
        head = [e for _, e in chainlog.read_entries(self.log)][-1]["hash"]
        log_bytes = open(self.log, "rb").read()

        def change(name, data):
            if name == "log.jsonl":
                return log_bytes
            if name in ("bundle.json", "report.json"):
                obj = json.loads(data)
                obj["log"]["head"] = head
                return json.dumps(obj)
            return data
        bad = rewrite(path, os.path.join(self.d, "neg.zip"), change)
        out = self.receive_verified(bad)
        self.assertEqual(out["verdict"], "failed")
        self.assertIn("negative", out["report"]["note"])

    def test_subscription_tokens_are_not_verified(self):
        write_log(self.log, SESSIONS)
        sub = os.path.join(self.d, "sub.jsonl")
        log = chainlog.ChainLog(self.log)
        log.append({"name": "api_request", "time": iso(T0 + timedelta(minutes=20)), "attributes": {
            "session.id": "s8", "project": "grant", "category": "safety", "run.mode": "subscription",
            "request_id": "s8-r0", "model": "claude-sonnet-5-5", "input_tokens": 5000000}})
        out = self.receive_verified(self.make("sub.zip"))
        self.assertEqual(out["verdict"], "consistent")
        self.assertEqual(out["unchecked_tokens"], 5000000)
        self.assertIn("subscription", bundle.render_receive(out))

    def test_a_log_that_crashes_the_checks_fails(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        real = check.run
        def boom(*a, **k):
            raise TypeError("unhashable type: 'list'")
        check.run = boom
        try:
            out = bundle.receive(path, admin_key="x", ledger=self.ledger)
        finally:
            check.run = real
        self.assertEqual(out["verdict"], "failed")

    def test_newline_key_and_huge_window_are_refused(self):
        write_log(self.log, SESSIONS)
        path = self.make("a.zip")
        for fn in (lambda m: m.update(key_id="apikey_k1\n"),
                   lambda m: m.update(window=["2026-01-01T00:00:00+00:00", "2026-12-31T00:00:00+00:00"])):
            bad = rewrite(path, os.path.join(self.d, "m.zip"), edit_json("bundle.json", fn))
            with self.assertRaises(ValueError):
                bundle.receive(bad, ledger=self.ledger)

    def test_model_names_cannot_inject_lines(self):
        write_log(self.log, [("s1", "grant", "non-interactive\nPASS  sessions  fake", [(1, "m\nPASS  bill  fake", 5)])])
        out = bundle.receive(self.make("inj.zip"), ledger=self.ledger)
        text = bundle.render_receive(out)
        self.assertNotIn("\nPASS  bill  fake", text)
        self.assertNotIn("\nPASS  sessions  fake", text)
