import unittest

from labkit.evals.agreement import cohens_kappa


class KappaTest(unittest.TestCase):
    def test_known_value(self):
        self.assertAlmostEqual(cohens_kappa([1, 1, 0, 0], [1, 0, 0, 0]), 0.5)

    def test_perfect(self):
        self.assertAlmostEqual(cohens_kappa(["a", "b", "a"], ["a", "b", "a"]), 1.0)

    def test_single_label(self):
        self.assertEqual(cohens_kappa(["x", "x"], ["x", "x"]), 1.0)

    def test_errors(self):
        with self.assertRaises(ValueError):
            cohens_kappa([1], [1, 0])
        with self.assertRaises(ValueError):
            cohens_kappa([], [])
