import unittest

from labkit.evals.contamination import find_overlaps


class OverlapTest(unittest.TestCase):
    def test_trigrams(self):
        train = ["the quick brown fox jumps"]
        items = ["a quick brown fox", "lazy dog sleeps", "THE QUICK brown", "quick brown"]
        self.assertEqual(find_overlaps(train, items, n=3), [0, 2])

    def test_default_n(self):
        train = ["one two three four five six seven eight nine"]
        items = ["two three four five six seven eight nine", "one two three"]
        self.assertEqual(find_overlaps(train, items), [0])
