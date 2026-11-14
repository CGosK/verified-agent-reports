"""Hidden checks for s4_redact."""
import unittest
from labkit.safety.redact import redact


class Hidden(unittest.TestCase):
    def test_phone_forms(self):
        for p in ("555-123-4567", "(555) 123 4567", "+1 555.123.4567", "5551234567", "+1-555-123-4567"):
            self.assertEqual(redact("call %s now" % p), "call [PHONE] now", p)

    def test_email_and_rest_unchanged(self):
        self.assertEqual(redact("mail a.b+c@ex-ample.co.uk, ref 12345"), "mail [EMAIL], ref 12345")


if __name__ == "__main__":
    unittest.main()
