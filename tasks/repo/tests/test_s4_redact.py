import unittest

from labkit.safety.redact import redact


class RedactTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(redact("mail me at a.b@example.org"), "mail me at [EMAIL]")

    def test_phones(self):
        self.assertEqual(redact("call 555-123-4567 now"), "call [PHONE] now")
        self.assertEqual(redact("(555) 123 4567"), "[PHONE]")
        self.assertEqual(redact("+1 555.123.4567"), "[PHONE]")

    def test_untouched(self):
        self.assertEqual(redact("order 12345 shipped"), "order 12345 shipped")
