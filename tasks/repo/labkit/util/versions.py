def compare_versions(a, b):
    """Compare dotted numeric versions such as "1.10.2".

    Return -1, 0 or 1. Missing parts count as 0, so "1.2" equals "1.2.0".
    Raise ValueError if any part isn't a non-negative integer.
    """
    raise NotImplementedError
