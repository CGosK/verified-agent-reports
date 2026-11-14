import unittest

from labkit.util.table import render_table


class TableTest(unittest.TestCase):
    def test_render(self):
        expected = "| name | n  |\n| ---- | -- |\n| a    | 1  |\n| bbb  | 22 |"
        self.assertEqual(render_table(["name", "n"], [["a", 1], ["bbb", 22]]), expected)

    def test_bad_row(self):
        with self.assertRaises(ValueError):
            render_table(["a", "b"], [["x"]])
