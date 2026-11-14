def parse_duration(text):
    """Parse a duration such as "1h30m", "45s", "2d" or "1h 5s" into seconds.

    Units are d, h, m and s, in any case, each preceded by a whole number.
    Spaces between parts are allowed. Return an int. Raise ValueError for an
    empty string or anything else that doesn't fit this format.
    """
    raise NotImplementedError
