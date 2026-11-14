import unittest

from labkit.util.durations import parse_duration


class DurationTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("2d"), 172800)
        self.assertEqual(parse_duration("1H 5S"), 3605)

    def test_errors(self):
        for bad in ("", "5x", "h", "1h30"):
            with self.assertRaises(ValueError):
                parse_duration(bad)
