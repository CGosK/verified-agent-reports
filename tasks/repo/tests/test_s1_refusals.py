import unittest

from labkit.evals.refusals import refusal_rate


class RefusalRateTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(refusal_rate([]), 0.0)

    def test_mixed_case_and_missing_key(self):
        records = [
            {"response": "I can't help with that."},
            {"response": "Sure, here it is."},
            {"response": "I MUST DECLINE."},
            {},
        ]
        self.assertAlmostEqual(refusal_rate(records), 0.5)

    def test_no_refusals(self):
        self.assertEqual(refusal_rate([{"response": "ok"}]), 0.0)
