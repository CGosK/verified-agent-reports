from collections import Counter


def count_ngrams(tokens, n):
    if n < 1:
        raise ValueError("n must be at least 1")
    return dict(Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)))
