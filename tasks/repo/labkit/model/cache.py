class LRUCache:
    """Least-recently-used cache with a fixed capacity.

    get(key, default=None) returns the value and marks the key as recently
    used. put(key, value) inserts or updates the key and marks it recently
    used, evicting the least recently used key when over capacity. len()
    returns the number of keys. Raise ValueError for capacity < 1.
    """

    def __init__(self, capacity):
        raise NotImplementedError

    def get(self, key, default=None):
        raise NotImplementedError

    def put(self, key, value):
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError
