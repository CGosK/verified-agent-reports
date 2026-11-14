import unittest

from labkit.model.ngrams import count_ngrams


class NgramTest(unittest.TestCase):
    def test_bigrams(self):
        self.assertEqual(count_ngrams(["a", "b", "a", "b"], 2), {("a", "b"): 2, ("b", "a"): 1})

    def test_short_and_errors(self):
        self.assertEqual(count_ngrams(["a"], 2), {})
        with self.assertRaises(ValueError):
            count_ngrams(["a"], 0)
