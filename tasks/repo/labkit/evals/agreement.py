def cohens_kappa(a, b):
    """Cohen's kappa between two graders' labels for the same items.

    `a` and `b` are equal-length lists of hashable labels. Raise ValueError if
    they are empty or differ in length. When expected agreement is 1 (both
    graders used one identical label throughout), return 1.0.
    """
    raise NotImplementedError
