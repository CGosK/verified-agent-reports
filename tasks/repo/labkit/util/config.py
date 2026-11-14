def deep_merge(base, override):
    """Return a new dict with override merged into base.

    When both sides hold a dict under the same key, merge them recursively;
    otherwise the override's value wins. Neither input is modified.
    """
    raise NotImplementedError
