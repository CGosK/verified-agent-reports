import filecmp
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PluginCopyTest(unittest.TestCase):
    def test_plugin_package_matches_vawr(self):
        src, dst = os.path.join(ROOT, "vawr"), os.path.join(ROOT, "plugin", "vawr")
        names = sorted(f for f in os.listdir(src) if f.endswith(".py"))
        self.assertEqual(names, sorted(f for f in os.listdir(dst) if f.endswith(".py")))
        match, mismatch, errors = filecmp.cmpfiles(src, dst, names, shallow=False)
        self.assertEqual(mismatch + errors, [], "run: rsync -a --delete --exclude __pycache__ vawr/ plugin/vawr/")
