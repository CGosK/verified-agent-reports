"""Hidden checks for s5_monitor."""
import unittest
from labkit.safety.monitor import flag_transcripts


class Hidden(unittest.TestCase):
    def test_order_by_transcript_then_pattern(self):
        self.assertEqual(flag_transcripts(["b then a", "only a"], ["a", "b"]),
                         [(0, "a"), (0, "b"), (1, "a")])

    def test_case_insensitive_regex_and_no_match(self):
        self.assertEqual(flag_transcripts(["EXFIL data", "fine"], [r"exf\w+", "zzz"]), [(0, r"exf\w+")])
        self.assertEqual(flag_transcripts([], ["a"]), [])


if __name__ == "__main__":
    unittest.main()
