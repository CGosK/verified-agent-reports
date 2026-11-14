from collections import Counter


def cohens_kappa(a, b):
    if not a or len(a) != len(b):
        raise ValueError("label lists must be non-empty and equal length")
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)
