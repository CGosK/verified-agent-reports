"""Every task's test must fail on the stub and pass with the reference
solution, so a passing test after a run means the agent did the work."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = json.load(open(os.path.join(REPO, "tasks", "tasks.json")))


def run_test(root, module):
    return subprocess.run([sys.executable, "-m", "unittest", module], cwd=root,
                          capture_output=True, text=True, timeout=60).returncode


class TaskSuiteTest(unittest.TestCase):
    def test_fifteen_tasks_five_per_category(self):
        self.assertEqual(len(TASKS), 15)
        cats = [t["category"] for t in TASKS]
        for c in ("safety", "capabilities", "other"):
            self.assertEqual(cats.count(c), 5)

    def test_stub_fails_and_solution_passes(self):
        for task in TASKS:
            with self.subTest(task=task["id"]), tempfile.TemporaryDirectory() as tmp:
                root = os.path.join(tmp, "repo")
                shutil.copytree(os.path.join(REPO, "tasks", "repo"), root)
                self.assertNotEqual(run_test(root, task["test"]), 0, "stub should fail")
                shutil.copy(os.path.join(REPO, "tasks", "solutions", task["id"] + ".py"),
                            os.path.join(root, task["path"]))
                self.assertEqual(run_test(root, task["test"]), 0, "solution should pass")


if __name__ == "__main__":
    unittest.main()
