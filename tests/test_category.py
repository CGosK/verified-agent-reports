import unittest

from vawr import category


def fake(picks):
    """A stand-in for the model call: picks[prompt] is its answer."""
    def classify_fn(task_prompt, diff):
        return {"category": picks[task_prompt], "reason": "test"}
    return classify_fn


def manifest(rid, true, prompt):
    return {"run_id": rid, "task": rid, "mode": "sprint", "true_category": true,
            "prompt": prompt, "diff": "diff --git a/x b/x"}


class DeclaredLabelsTest(unittest.TestCase):
    def test_one_label_per_run_and_mixed(self):
        reqs = [{"run_id": "a", "category": "safety"}, {"run_id": "a", "category": "safety"},
                {"run_id": "b", "category": "safety"}, {"run_id": "b", "category": "other"},
                {"run_id": None, "category": "other"}]
        self.assertEqual(category.declared_labels(reqs), {"a": "safety", "b": "mixed"})


class CheckRunsTest(unittest.TestCase):
    def setUp(self):
        self.ms = [manifest("a", "safety", "pa"), manifest("b", "capabilities", "pb"),
                   manifest("off", "other", "poff")]
        self.picks = fake({"pa": "safety", "pb": "other", "poff": "other"})

    def test_flags_only_disagreements_and_skips_off_log_runs(self):
        rows = category.check_runs(self.ms, {"a": "safety", "b": "capabilities"}, {}, self.picks)
        self.assertEqual([(r["run_id"], r["flagged"]) for r in rows], [("a", False), ("b", True)])

    def test_verdicts_are_cached_per_prompt_version(self):
        cache = {}
        category.check_runs(self.ms, {"a": "safety"}, cache, self.picks)
        self.assertEqual(list(cache), ["%s|a" % category.PROMPT_SHA])
        boom = fake({})  # would raise KeyError if called
        rows = category.check_runs(self.ms, {"a": "safety"}, cache, boom)
        self.assertEqual(rows[0]["classified"], "safety")

    def test_relabels_caught_when_pick_differs_from_new_tag(self):
        rows = category.check_runs(self.ms, {"a": "safety", "b": "capabilities"}, {}, self.picks)
        trials = category.relabel_trials(rows)
        self.assertEqual(len(trials), 4)
        caught = {(t["run_id"], t["to"]): t["caught"] for t in trials}
        # a is picked correctly: both relabels caught
        self.assertTrue(caught[("a", "capabilities")] and caught[("a", "other")])
        # b is picked as other: relabel to safety caught, relabel to other missed
        self.assertTrue(caught[("b", "safety")])
        self.assertFalse(caught[("b", "other")])


class VerdictTest(unittest.TestCase):
    def test_three_verdicts(self):
        self.assertEqual(category.verdict("safety", "safety"), "confirmed")
        self.assertEqual(category.verdict("safety", "other"), "unconfirmed")
        self.assertEqual(category.verdict("safety", "capabilities"), "contradicted")
        self.assertEqual(category.verdict("other", "safety"), "contradicted")


if __name__ == "__main__":
    unittest.main()
