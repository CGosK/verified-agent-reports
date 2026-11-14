import unittest

from labkit.model.sampling import top_k_filter

NEG = float("-inf")


class TopKTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(top_k_filter([1.0, 3.0, 2.0, 0.5], 2), [NEG, 3.0, 2.0, NEG])

    def test_ties_kept(self):
        self.assertEqual(top_k_filter([1, 2, 2, 0], 2), [NEG, 2, 2, NEG])
        self.assertEqual(top_k_filter([1, 2, 2, 0], 3), [1, 2, 2, NEG])

    def test_large_k_and_errors(self):
        self.assertEqual(top_k_filter([1, 2], 10), [1, 2])
        with self.assertRaises(ValueError):
            top_k_filter([1, 2], 0)
