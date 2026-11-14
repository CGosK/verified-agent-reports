import unittest

from labkit.util.config import deep_merge


class MergeTest(unittest.TestCase):
    def test_merge(self):
        base = {"a": 1, "nested": {"x": 1, "y": 2}, "keep": [1]}
        override = {"a": 2, "nested": {"y": 3, "z": 4}, "new": True}
        merged = deep_merge(base, override)
        self.assertEqual(merged, {"a": 2, "nested": {"x": 1, "y": 3, "z": 4}, "keep": [1], "new": True})
        self.assertEqual(base, {"a": 1, "nested": {"x": 1, "y": 2}, "keep": [1]})
        self.assertEqual(override, {"a": 2, "nested": {"y": 3, "z": 4}, "new": True})

    def test_override_dict_with_scalar(self):
        self.assertEqual(deep_merge({"a": {"b": 1}}, {"a": 5}), {"a": 5})
