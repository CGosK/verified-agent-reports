"""Hidden checks for s3_contamination."""
import unittest
from labkit.evals.contamination import find_overlaps


class Hidden(unittest.TestCase):
    def test_short_items_never_match(self):
        self.assertEqual(find_overlaps(["a b c d"], ["a b", "a b c"], n=3), [1])

    def test_case_in_items_and_docs(self):
        self.assertEqual(find_overlaps(["Alpha BETA gamma"], ["alpha beta GAMMA delta"], n=3), [0])

    def test_several_docs_sorted(self):
        train = ["red green blue", "one two three"]
        items = ["x one two three", "nothing here at all", "red green blue y"]
        self.assertEqual(find_overlaps(train, items, n=3), [0, 2])


if __name__ == "__main__":
    unittest.main()
