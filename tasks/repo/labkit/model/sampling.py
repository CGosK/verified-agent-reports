def top_k_filter(logits, k):
    """Keep the k largest logits and set every other entry to float("-inf").

    Return a new list in the original order. Values tied with the k-th
    largest value are all kept. Raise ValueError if k < 1. If k is at least
    the list length, return an unchanged copy.
    """
    raise NotImplementedError
