import unittest

from labkit.util.text import slugify


class SlugTest(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
        self.assertEqual(slugify("  Café  Déjà vu "), "cafe-deja-vu")
        self.assertEqual(slugify("---"), "")
        self.assertEqual(slugify("Q3 2026 plan"), "q3-2026-plan")
