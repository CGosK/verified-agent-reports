"""Hidden checks for s2_agreement."""
import unittest
from labkit.evals.agreement import cohens_kappa


class Hidden(unittest.TestCase):
    def test_errors(self):
        with self.assertRaises(ValueError):
            cohens_kappa([], [])
        with self.assertRaises(ValueError):
            cohens_kappa(["a"], ["a", "b"])

    def test_one_label_throughout(self):
        self.assertEqual(cohens_kappa(["x", "x", "x"], ["x", "x", "x"]), 1.0)

    def test_value(self):
        a = ["y", "y", "n", "n", "y", "n"]
        b = ["y", "n", "n", "n", "y", "y"]
        self.assertAlmostEqual(cohens_kappa(a, b), 1 / 3)


if __name__ == "__main__":
    unittest.main()
