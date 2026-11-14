import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from vawr import chainlog, check, configure, receiver
from vawr.logdata import api_requests

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)


def kv(k, v):
    return {"key": k, "value": {"stringValue": v}}


class ReceiverAuthTest(unittest.TestCase):
    def test_plan_becomes_auth_account_and_is_dropped(self):
        a = receiver.attrs([kv("anthropic.plan", "max"), kv("anthropic.seat_type", "standard"),
                            kv("anthropic.provider", "firstParty"), kv("user.email", "x@y.z")])
        self.assertEqual(a.get("auth"), "account")
        for k in ("anthropic.plan", "anthropic.seat_type", "user.email"):
            self.assertNotIn(k, a)

    def test_no_plan_means_api_key(self):
        self.assertEqual(receiver.attrs([kv("anthropic.provider", "firstParty")]).get("auth"), "api_key")

    def test_resource_without_provider_gets_no_auth(self):
        self.assertNotIn("auth", receiver.attrs([kv("service.name", "claude-code")]))


class ConfigureTest(unittest.TestCase):
    def test_merge_keeps_other_settings_and_backs_up(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            json.dump({"theme": "dark", "env": {"FOO": "1"}}, open(path, "w"))
            changes, _ = configure.merge_env(path, {"BAR": "2"}, write=False)
            self.assertEqual(changes, [("BAR", None, "2")])
            self.assertEqual(json.load(open(path))["env"], {"FOO": "1"})  # dry run wrote nothing
            configure.merge_env(path, {"BAR": "2"}, write=True)
            self.assertEqual(json.load(open(path)), {"theme": "dark", "env": {"FOO": "1", "BAR": "2"}})
            self.assertEqual(len([f for f in os.listdir(d) if ".vawr-backup-" in f]), 1)

    def test_tag_rejects_unknown_category(self):
        with self.assertRaises(SystemExit):
            configure.tag_env("marketing", "p")


class CheckCoverageTest(unittest.TestCase):
    def test_unlogged_session_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            projects = os.path.join(d, "projects")
            os.makedirs(os.path.join(projects, "proj"))
            t = (T0 + timedelta(minutes=3, seconds=20)).isoformat().replace("+00:00", "Z")
            usage = {"input_tokens": 5, "output_tokens": 5, "cache_read_input_tokens": 0,
                     "cache_creation_input_tokens": 0}
            with open(os.path.join(projects, "proj", "s1.jsonl"), "w") as fh:
                for rid in ("r1", "r2"):
                    fh.write(json.dumps({"type": "assistant", "requestId": rid, "sessionId": "s1",
                                         "timestamp": t, "message": {"model": "m", "usage": usage}}) + "\n")
            log = os.path.join(d, "events.jsonl")
            chainlog.ChainLog(log).append({"name": "api_request", "time": t, "attributes": {
                "request_id": "r1", "session.id": "s1", "model": "m", "input_tokens": 5,
                "output_tokens": 5, "cache_read_tokens": 0, "cache_creation_tokens": 0,
                "anthropic.provider": "firstParty", "auth": "api_key"}, "resource": {}})
            res = check.run(T0, T0 + timedelta(minutes=10), log, projects)
            self.assertTrue(res["chain"]["ok"])
            self.assertFalse(res["coverage"]["ok"])
            self.assertEqual(res["coverage"]["unlogged_sessions"][0]["requests"], 1)


if __name__ == "__main__":
    unittest.main()
