def warmup_cosine(step, warmup, total, base_lr, min_lr=0.0):
    """Learning rate with linear warmup then cosine decay.

    For step < warmup: base_lr * (step + 1) / warmup.
    Otherwise: progress = (step - warmup) / max(1, total - warmup), clamped to
    [0, 1], and lr = min_lr + 0.5 * (base_lr - min_lr) * (1 + cos(pi * progress)).
    """
    raise NotImplementedError
