def pack_sequences(lengths, max_tokens):
    """Pack sequences into batches of at most max_tokens total length.

    Visit sequences by decreasing length (ties by lower index first). Put each
    into the first existing batch whose total stays <= max_tokens; otherwise
    open a new batch. Return the batches in the order they were opened, each
    a list of sequence indices sorted ascending. Raise ValueError if any
    sequence is longer than max_tokens.
    """
    raise NotImplementedError
