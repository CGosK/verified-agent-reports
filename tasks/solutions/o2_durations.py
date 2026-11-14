import re

UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
PART = re.compile(r"\s*(\d+)\s*([dhms])\s*", re.IGNORECASE)


def parse_duration(text):
    if not text or not text.strip():
        raise ValueError("empty duration")
    pos, total = 0, 0
    while pos < len(text):
        m = PART.match(text, pos)
        if not m:
            raise ValueError("bad duration: %r" % text)
        total += int(m.group(1)) * UNITS[m.group(2).lower()]
        pos = m.end()
    return total
