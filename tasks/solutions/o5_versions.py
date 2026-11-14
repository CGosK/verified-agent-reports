def _parts(v):
    parts = v.split(".")
    if not all(p.isdigit() for p in parts):
        raise ValueError("bad version: %r" % v)
    return [int(p) for p in parts]


def compare_versions(a, b):
    pa, pb = _parts(a), _parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)
