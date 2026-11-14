import re


def flag_transcripts(transcripts, patterns):
    compiled = [(p, re.compile(p, re.IGNORECASE)) for p in patterns]
    return [(i, p) for i, t in enumerate(transcripts) for p, rx in compiled if rx.search(t)]
