def _grams(text, n):
    words = text.lower().split()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def find_overlaps(train_docs, test_items, n=8):
    seen = set()
    for doc in train_docs:
        seen |= _grams(doc, n)
    return [i for i, item in enumerate(test_items) if _grams(item, n) & seen]
