def pack_sequences(lengths, max_tokens):
    if any(n > max_tokens for n in lengths):
        raise ValueError("sequence longer than max_tokens")
    order = sorted(range(len(lengths)), key=lambda i: (-lengths[i], i))
    batches, totals = [], []
    for i in order:
        for b, t in enumerate(totals):
            if t + lengths[i] <= max_tokens:
                batches[b].append(i)
                totals[b] += lengths[i]
                break
        else:
            batches.append([i])
            totals.append(lengths[i])
    return [sorted(b) for b in batches]
