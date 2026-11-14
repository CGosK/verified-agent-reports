import unittest

from labkit.model.cache import LRUCache


class CacheTest(unittest.TestCase):
    def test_eviction(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.get("a"), 1)
        c.put("c", 3)
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(len(c), 2)

    def test_update_refreshes(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 10)
        c.put("c", 3)
        self.assertEqual(c.get("a"), 10)
        self.assertEqual(c.get("b", "gone"), "gone")

    def test_bad_capacity(self):
        with self.assertRaises(ValueError):
            LRUCache(0)
