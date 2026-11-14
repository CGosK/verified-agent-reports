def flag_transcripts(transcripts, patterns):
    """Flag transcripts that match monitor patterns.

    `patterns` are regular expressions matched case-insensitively against each
    transcript string. Return a list of (transcript_index, pattern) pairs for
    every match, ordered by transcript index and then by pattern order.
    """
    raise NotImplementedError
