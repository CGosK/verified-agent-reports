"""Exact (Clopper-Pearson) binomial confidence intervals, stdlib only."""

import math


def _binom_cdf(k, n, p):
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < n else 1.0
    total = 0.0
    for i in range(0, k + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return min(1.0, total)


def _bisect(f, lo=0.0, hi=1.0, iters=80):
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid):
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    """Two-sided exact interval for k successes in n trials."""
    if n == 0:
        return (0.0, 1.0)
    lower = 0.0 if k == 0 else _bisect(lambda p: _binom_cdf(k - 1, n, p) <= 1 - alpha / 2)
    upper = 1.0 if k == n else _bisect(lambda p: _binom_cdf(k, n, p) <= alpha / 2)
    return (lower, upper)


def rate(k, n, alpha=0.05):
    lo, hi = clopper_pearson(k, n, alpha)
    return {"k": k, "n": n, "rate": (k / n) if n else None, "ci95": [round(lo, 4), round(hi, 4)]}
