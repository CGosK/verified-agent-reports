import unittest

from labkit.model.schedule import warmup_cosine


class ScheduleTest(unittest.TestCase):
    def test_points(self):
        f = lambda s, **kw: warmup_cosine(s, warmup=10, total=110, base_lr=1.0, **kw)
        self.assertAlmostEqual(f(0), 0.1)
        self.assertAlmostEqual(f(9), 1.0)
        self.assertAlmostEqual(f(10), 1.0)
        self.assertAlmostEqual(f(60), 0.5)
        self.assertAlmostEqual(f(110), 0.0)
        self.assertAlmostEqual(f(200), 0.0)
        self.assertAlmostEqual(f(110, min_lr=0.1), 0.1)
