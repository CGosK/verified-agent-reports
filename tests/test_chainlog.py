import json
import os
import tempfile
import unittest

from vawr import chainlog
from vawr.receiver import DROPPED_ATTRIBUTES, flatten_logs, flatten_metrics


def write_log(path, n=5):
    log = chainlog.ChainLog(path)
    for i in range(n):
        log.append({"name": "api_request", "attributes": {"request_id": "req_%d" % i, "input_tokens": i}})


def rewrite(path, entries):
    with open(path, "w") as fh:
        for e in entries:
            fh.write(chainlog.canonical(e) + "\n")


class ChainLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "log.jsonl")
        write_log(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def entries(self):
        return [e for _, e in chainlog.read_entries(self.path)]

    def test_clean_log_verifies(self):
        ok, problems, count, head = chainlog.verify(self.path)
        self.assertTrue(ok, problems)
        self.assertEqual(count, 5)
        self.assertEqual(head, self.entries()[-1]["hash"])

    def test_reopen_continues_chain(self):
        write_log(self.path, 2)
        ok, problems, count, _ = chainlog.verify(self.path)
        self.assertTrue(ok, problems)
        self.assertEqual(count, 7)

    def test_deleted_entry_fails(self):
        es = self.entries()
        del es[2]
        rewrite(self.path, es)
        self.assertFalse(chainlog.verify(self.path)[0])

    def test_edited_entry_fails(self):
        es = self.entries()
        es[1]["event"]["attributes"]["input_tokens"] = 0
        rewrite(self.path, es)
        self.assertFalse(chainlog.verify(self.path)[0])

    def test_truncated_tail_passes_chain_check(self):
        # Known limit: the chain can't see a dropped tail. The completeness
        # checks (session files, provider usage) are what catch it.
        rewrite(self.path, self.entries()[:3])
        self.assertTrue(chainlog.verify(self.path)[0])


class ReceiverTest(unittest.TestCase):
    def test_flatten_drops_identity(self):
        payload = {"resourceLogs": [{
            "resource": {"attributes": [{"key": "category", "value": {"stringValue": "safety"}}]},
            "scopeLogs": [{"logRecords": [{
                "timeUnixNano": "1763049600000000000",
                "body": {"stringValue": "claude_code.api_request"},
                "attributes": [
                    {"key": "event.name", "value": {"stringValue": "api_request"}},
                    {"key": "input_tokens", "value": {"intValue": "12"}},
                    {"key": "user.email", "value": {"stringValue": "someone@example.com"}},
                ]}]}]}]}
        events = list(flatten_logs(payload))
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "api_request")
        self.assertEqual(ev["attributes"]["input_tokens"], 12)
        self.assertEqual(ev["resource"]["category"], "safety")
        self.assertFalse(set(ev["attributes"]) & DROPPED_ATTRIBUTES)


class MetricsTest(unittest.TestCase):
    def test_keeps_token_usage_and_drops_others(self):
        point = {"timeUnixNano": "1763049600000000000", "startTimeUnixNano": "1763049595000000000",
                 "asDouble": 7010,
                 "attributes": [{"key": "type", "value": {"stringValue": "cacheRead"}},
                                {"key": "query_source", "value": {"stringValue": "auxiliary"}},
                                {"key": "user.email", "value": {"stringValue": "x@example.com"}}]}
        payload = {"resourceMetrics": [{"resource": {"attributes": []}, "scopeMetrics": [{"metrics": [
            {"name": "claude_code.token.usage", "sum": {"aggregationTemporality": 1, "dataPoints": [point]}},
            {"name": "claude_code.session.count", "sum": {"dataPoints": [point]}},
        ]}]}]}
        events = list(flatten_metrics(payload))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["metric"], "claude_code.token.usage")
        self.assertEqual(events[0]["value"], 7010.0)
        self.assertNotIn("user.email", events[0]["attributes"])


if __name__ == "__main__":
    unittest.main()
