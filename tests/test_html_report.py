"""HTML report: renders from the sample outputs, leaves out sections whose
input is missing, and escapes every string taken from the inputs."""

import copy
import html
import json
import os
import unittest
from html.parser import HTMLParser

from vawr import html_report

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(REPO, "work", "samples")
HOSTILE = '<script>alert("x")</script><img src=x onerror=alert(1)>'
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def load(name):
    with open(os.path.join(SAMPLES, name)) as fh:
        return json.load(fh)


class Structure(HTMLParser):
    """Collects unbalanced tags and any attribute that would fetch something."""

    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.fetches = [], [], []

    def _attrs(self, tag, attrs):
        for k, v in attrs:
            if k in ("src", "href", "srcset") or (v and "url(" in v):
                self.fetches.append((tag, k, v))

    def handle_starttag(self, tag, attrs):
        self._attrs(tag, attrs)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._attrs(tag, attrs)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append("unexpected </%s> with open %s" % (tag, self.stack[-3:]))


def structure(doc):
    p = Structure()
    p.feed(doc)
    p.close()
    return p


class HtmlReportTest(unittest.TestCase):
    def setUp(self):
        self.report = load("report_batch1.json")
        self.check = load("check_batch1.json")
        self.billcheck = load("billcheck_batch1.json")
        self.categories = load("category_check.json")
        self.claims = load("claims_summary.json")

    def render_all(self, **kw):
        args = dict(check=self.check, billcheck=self.billcheck, categories=self.categories, claims=self.claims)
        args.update(kw)
        return html_report.render(self.report, **args)

    def assert_well_formed(self, doc):
        self.assertTrue(doc.startswith("<!doctype html>"))
        s = structure(doc)
        self.assertEqual(s.errors, [])
        self.assertEqual(s.stack, [])
        self.assertEqual(s.fetches, [], "the page must not load anything")
        self.assertNotIn("<script", doc.lower())

    def test_all_inputs(self):
        doc = self.render_all()
        self.assert_well_formed(doc)
        self.assertIn(self.report["log"]["head"], doc)
        for c in self.report["categories"]:
            self.assertIn(">%s<" % c["category"], doc)
        for key in ("chain", "coverage", "bill", "category", "claims"):
            self.assertIn('id="check-%s"' % key, doc)
        # sections in order: verdict, usage, checks, how to verify, footer
        marks = ['class="verdict', 'id="usage"', 'id="checks"', 'id="verify"', "<footer>"]
        positions = [doc.index(m) for m in marks]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("need attention", doc)
        # the re-run command carries the check's window and the log path
        start, end = self.check["window"]
        path = self.report["log"]["path"]
        self.assertIn("vawr check --no-coverage --since %s \\\n    --until %s \\\n    --log %s" % (start, end, path), doc)
        self.assertIn("vawr status --log %s" % path, doc)
        self.assertIn("vawr verify-report report.json --log %s" % path, doc)
        # every unexplained billed minute is listed, with the total the CLI would print
        gap = sum(sum(g["tokens"].values()) for g in self.check["bill"]["gaps"])
        self.assertIn("{:,}".format(gap), doc)
        for g in self.check["bill"]["gaps"]:
            self.assertIn(g["start"][11:16], doc)
        # flagged labels for this report's runs come with the model's reason
        run_ids = {r["run_id"] for r in self.report["runs"]}
        flagged = [r for r in self.categories["rows"] if r["run_id"] in run_ids and r["flagged"]]
        self.assertTrue(flagged)
        for r in flagged:
            self.assertIn(html.escape(r["reason"]), doc)
        # rows for runs outside this report are left out
        outside = [r for r in self.categories["rows"] if r["run_id"] not in run_ids and r["flagged"]]
        for r in outside:
            self.assertNotIn(r["run_id"], doc)

    def test_report_only(self):
        doc = html_report.render(self.report)
        self.assert_well_formed(doc)
        self.assertIn(self.report["log"]["head"], doc)
        for c in self.report["categories"]:
            self.assertIn(">%s<" % c["category"], doc)
        self.assertIn('id="check-chain"', doc)
        for key in ("coverage", "bill", "category", "claims"):
            self.assertNotIn('id="check-%s"' % key, doc)
        self.assertIn("Not included in this report: coverage, bill, category, claims", doc)
        self.assertIn("--since &lt;start&gt; \\\n    --until &lt;end&gt;", doc)

    def test_escapes_hostile_strings(self):
        report = copy.deepcopy(self.report)
        report["categories"][0]["category"] = HOSTILE
        report["note"] = HOSTILE
        report["log"]["path"] = HOSTILE
        report["runs"][0]["run_id"] = HOSTILE
        cats = copy.deepcopy(self.categories)
        run_ids = {r["run_id"] for r in report["runs"]}
        row = next(r for r in cats["rows"] if r["run_id"] in run_ids and r["flagged"])
        row["reason"] = HOSTILE
        row["task"] = HOSTILE
        check = copy.deepcopy(self.check)
        check["coverage"]["unlogged_sessions"][0]["project"] = HOSTILE
        check["bill"]["gaps"][0]["by_model"] = {HOSTILE: {"input": 1}}
        doc = html_report.render(report, check=check, billcheck=self.billcheck, categories=cats,
                                 claims=self.claims, title=HOSTILE)
        self.assert_well_formed(doc)
        self.assertNotIn(HOSTILE, doc)
        self.assertNotIn("<img", doc)
        self.assertIn(html.escape(HOSTILE), doc)

    def test_all_passing_inputs(self):
        check = copy.deepcopy(self.check)
        check["coverage"].update(ok=True, unlogged_sessions=[], token_mismatches=0)
        check["bill"].update(gaps=[], log_excess=[])
        billcheck = dict(self.billcheck, gaps=[], log_excess=[])
        cats = copy.deepcopy(self.categories)
        for r in cats["rows"]:
            r.update(classified=r["declared"], flagged=False, verdict="confirmed")
        claims = dict(self.claims, real_runs_flagged={"k": 0, "n": 52, "rate": 0.0, "ci95": [0.0, 0.07]})
        doc = html_report.render(self.report, check=check, billcheck=billcheck, categories=cats, claims=claims)
        self.assert_well_formed(doc)
        self.assertIn("All 5 checks passed", doc)
        self.assertNotIn('class="badge fail"', doc)

    def test_bill_without_admin_key_is_skipped(self):
        check = dict(self.check, bill=None)
        doc = html_report.render(self.report, check=check)
        self.assertIn('id="check-bill"><h3><span class="badge skip">', doc)
        self.assertIn("Not run: bill", doc)

    def test_check_on_other_log_version_warns(self):
        check = copy.deepcopy(self.check)
        check["chain"].update(head="f" * 64, entries=600)
        doc = html_report.render(self.report, check=check)
        self.assertIn("different version of the log", doc)


if __name__ == "__main__":
    unittest.main()
