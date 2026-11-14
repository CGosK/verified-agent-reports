def find_overlaps(train_docs, test_items, n=8):
    """Indices of test items that share a word n-gram with any training doc.

    Words are whitespace-separated and compared in lower case. An item with
    fewer than `n` words never matches. Return the indices sorted ascending.
    """
    raise NotImplementedError
