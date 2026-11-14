import unittest

from labkit.util.versions import compare_versions


class VersionTest(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(compare_versions("1.2", "1.2.0"), 0)
        self.assertEqual(compare_versions("1.10", "1.9"), 1)
        self.assertEqual(compare_versions("2.0.1", "2.1"), -1)

    def test_bad(self):
        with self.assertRaises(ValueError):
            compare_versions("1.a", "1.0")
