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

    def make(self, name, log=None, **kw):
        out = os.path.join(self.d, name)
        kw.setdefault("key_id", "k1")
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
        res = daily.check(None, "k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"], now=NOW,
                          key_name="grant key", fetch=lambda d: recs)
        self.assertEqual(res["days"][0]["status"], "pass")  # equal counts pass even on the log's first day
        self.assertEqual([c["status"] for c in res["days"][0]["by_terminal"]], ["pass", "pass"])
        self.assertEqual(res["days"][0]["work"]["commits"], 2)

    def test_hidden_session_fails_its_terminal(self):
        write_log(self.log, SESSIONS)
        recs = cc_records({"non-interactive": (2, {"claude-sonnet-5-5": 190}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = daily.check(None, "k1", T0, T0 + timedelta(hours=1), [self.log], only_projects=["grant"], now=NOW,
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
        self.assertFalse(out["continuity"]["ok"])
        self.assertEqual(out["verdict"], "failed")

    def test_log_rebuilt_from_first_entry_is_a_new_log_and_fails_for_the_same_key(self):
        write_log(self.log, SESSIONS)
        bundle.receive(self.make("first.zip"), ledger=self.ledger)
        entries = [e for _, e in chainlog.read_entries(self.log)]
        entries[0]["event"]["attributes"]["category"] = "capabilities"
        validate.rehash(entries)
        rebuilt = os.path.join(self.d, "rebuilt.jsonl")
        with open(rebuilt, "w") as fh:
            for e in entries:
                fh.write(chainlog.canonical(e) + "\n")
        out = bundle.receive(self.make("again.zip", log=rebuilt), ledger=self.ledger)
        self.assertFalse(out["continuity"]["ok"])

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
        org = {"k1": {minute(1): {"claude-sonnet-5-5": tok(100)}, minute(2): {"claude-sonnet-5-5": tok(50)},
                      minute(5): {"claude-haiku-5-5": tok(30)}},
               "k2": {minute(9): {"claude-opus-5-5": tok(500)}}}
        keys = [{"id": "k1", "name": "grant key"}, {"id": "k2", "name": "intern key"}]
        recs = cc_records({"non-interactive": (1, {"claude-sonnet-5-5": 150}),
                           "xterm-256color": (1, {"claude-haiku-5-5": 30})})
        res = team.run([path], None, ledger=self.ledger, org_minutes=org, keys=keys, fetch=lambda d: recs, now=NOW)
        by = {r["key_id"]: r for r in res["keys"]}
        self.assertEqual(by["k1"]["status"], "pass")
        self.assertEqual(by["k2"]["status"], "no report")
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
