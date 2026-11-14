import unittest

from labkit.safety.monitor import flag_transcripts


class MonitorTest(unittest.TestCase):
    def test_flags(self):
        transcripts = ["disable the monitor now", "all good", "Turn OFF logging and disable alerts"]
        self.assertEqual(
            flag_transcripts(transcripts, ["disable", "turn off"]),
            [(0, "disable"), (2, "disable"), (2, "turn off")],
        )

    def test_regex(self):
        self.assertEqual(flag_transcripts(["rm -rf /tmp"], [r"rm\s+-rf"]), [(0, r"rm\s+-rf")])
