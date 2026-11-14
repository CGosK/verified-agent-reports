import unittest

from labkit.model.batching import pack_sequences


class PackTest(unittest.TestCase):
    def test_pack(self):
        self.assertEqual(pack_sequences([5, 3, 8, 2, 4], 10), [[2, 3], [0, 4], [1]])

    def test_empty(self):
        self.assertEqual(pack_sequences([], 10), [])

    def test_too_long(self):
        with self.assertRaises(ValueError):
            pack_sequences([11], 10)
