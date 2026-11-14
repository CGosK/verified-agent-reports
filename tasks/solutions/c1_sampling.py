def top_k_filter(logits, k):
    if k < 1:
        raise ValueError("k must be at least 1")
    if k >= len(logits):
        return list(logits)
    cutoff = sorted(logits, reverse=True)[k - 1]
    return [x if x >= cutoff else float("-inf") for x in logits]
