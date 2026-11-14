import unittest
from datetime import datetime, timedelta, timezone

from vawr import auditor, stats

T0 = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)


def m(i):
    return T0 + timedelta(minutes=i)


def req(minute, tokens, mode="sprint", rid=None):
    return {"request_id": rid or "req_%d" % minute, "mode": mode,
            "time": (m(minute) + timedelta(seconds=30)).isoformat(),
            "tokens": {"input": tokens, "output": tokens, "cache_read": 0, "cache_creation": 0},
            "query_source": "sdk", "run_id": "r", "category": "safety", "cost_usd": 0}


def prov(minute, tokens):
    return {m(minute): {"input": tokens, "output": tokens, "cache_read": 0, "cache_creation": 0}}


class ProviderMatchTest(unittest.TestCase):
    def run_check(self, log, provider):
        return auditor.check_provider(log, m(0), m(20), shift=2, provider_minutes=provider)

    def test_exact_match_passes(self):
        res = self.run_check([req(3, 100), req(9, 50)], {**prov(3, 100), **prov(9, 50)})
        self.assertTrue(res["ok"], res)

    def test_minute_shift_tolerated(self):
        # logged one minute after the provider counted it
        res = self.run_check([req(4, 100)], prov(3, 100))
        self.assertTrue(res["ok"], res)

    def test_off_log_run_is_a_gap(self):
        res = self.run_check([req(3, 100)], {**prov(3, 100), **prov(12, 70)})
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["gaps"]), 1)
        self.assertEqual(res["gaps"][0]["tokens"]["input"], 70)

    def test_lowered_tokens_is_a_gap(self):
        res = self.run_check([req(3, 60)], prov(3, 100))
        self.assertEqual(res["gaps"][0]["tokens"]["input"], 40)

    def test_subscription_requests_ignored(self):
        res = self.run_check([req(3, 100), req(5, 999, mode="subscription")], prov(3, 100))
        self.assertTrue(res["ok"], res)

    def test_inflated_log_is_excess(self):
        res = self.run_check([req(3, 100), req(15, 40)], prov(3, 100))
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["log_excess"]), 1)


SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
BG = {"input": 300, "output": 200, "cache_read": 7010, "cache_creation": 0}


def mreq(minute, tokens, model=SONNET, session="s1"):
    r = req(minute, tokens)
    r.update(model=model, session_id=session)
    return r


def mprov(minute, by_model):
    return {m(minute): by_model}


def tok(n):
    return {"input": n, "output": n, "cache_read": 0, "cache_creation": 0}


class BackgroundRequestTest(unittest.TestCase):
    def run_check(self, log, provider):
        return auditor.check_provider(log, m(0), m(20), shift=2, provider_minutes=provider)

    def test_background_next_to_logged_session_is_allowed(self):
        res = self.run_check([mreq(3, 100)], mprov(3, {SONNET: tok(100), HAIKU: BG}))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["background_tokens"]["cache_read"], 7010)

    def test_background_without_a_logged_session_is_a_gap(self):
        res = self.run_check([mreq(3, 100)], {**mprov(3, {SONNET: tok(100), HAIKU: BG}), **mprov(12, {HAIKU: BG})})
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["gaps"]), 1)
        self.assertEqual(res["gaps"][0]["start"], m(12).isoformat())

    def test_per_session_background_share(self):
        res = self.run_check([mreq(3, 100, session="a"), mreq(9, 100, session="b")],
                             {**mprov(3, {SONNET: tok(100), HAIKU: BG}), **mprov(9, {SONNET: tok(100), HAIKU: BG})})
        a = res["per_session"]["a"]
        self.assertEqual(a["provider_tokens_in_span"], 200 + 7510)
        self.assertEqual(a["background_in_span"], 7510)
        self.assertAlmostEqual(a["background_share"], 7510 / 7710)
        self.assertFalse(a["span_shared"])

    def test_one_envelope_per_session(self):
        two = {k: 2 * v for k, v in BG.items()}
        res = self.run_check([mreq(3, 100)], mprov(3, {SONNET: tok(100), HAIKU: two}))
        self.assertFalse(res["ok"])

    def test_cache_creation_on_small_model_is_a_gap(self):
        work = dict(BG, cache_creation=3000)
        res = self.run_check([mreq(3, 100)], mprov(3, {SONNET: tok(100), HAIKU: work}))
        self.assertFalse(res["ok"])
        self.assertEqual(res["gaps"][0]["by_model"][HAIKU]["cache_creation"], 3000)

    def test_off_log_main_model_work_is_a_gap(self):
        res = self.run_check([mreq(3, 100)], {**mprov(3, {SONNET: tok(100)}), **mprov(9, {SONNET: tok(50)})})
        self.assertEqual(len(res["gaps"]), 1)


class StatsTest(unittest.TestCase):
    def test_known_intervals(self):
        lo, hi = stats.clopper_pearson(3, 3)
        self.assertAlmostEqual(lo, 0.2924, places=3)
        self.assertEqual(hi, 1.0)
        lo, hi = stats.clopper_pearson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.3085, places=3)


if __name__ == "__main__":
    unittest.main()
