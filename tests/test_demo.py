"""`vawr demo` runs offline: Anthropic's records come only from the saved responses."""
import io
import os
import tempfile
import unittest
import urllib.request

from vawr import demo


class DemoTest(unittest.TestCase):
    def test_three_verdicts_offline(self):
        real = urllib.request.urlopen

        def no_network(*a, **k):
            raise AssertionError("the demo tried to reach the network")
        urllib.request.urlopen = no_network
        out = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as d:
                verdicts = demo.run(html_dir=os.path.join(d, "pages"), out=out)
                pages = sorted(os.listdir(os.path.join(d, "pages")))
        finally:
            urllib.request.urlopen = real
        self.assertEqual(verdicts, ["verified", "failed", "failed"])
        text = out.getvalue()
        self.assertIn("430,844 tokens that the log doesn't account for", text)
        self.assertIn("replayed", text)
        self.assertIn("not run: the log or the report already failed", text)
        self.assertEqual(pages, ["batch-hidden.html", "full-day-edited.html", "full-day.html"])

    def test_saved_records_hold_no_key_hints_or_other_actors(self):
        with open(demo.RECORDS) as fh:
            text = fh.read()
        for bad in ("partial_key_hint", "sk-ant-", "email", "created_by"):
            self.assertNotIn(bad, text)


if __name__ == "__main__":
    unittest.main()
