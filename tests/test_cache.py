import time

from cinecritic.cache import TTLCache


def test_ttl_expiry():
    cache = TTLCache(0.02, 4)
    cache.set("k", 1)
    assert cache.get("k") == 1
    time.sleep(0.05)
    assert cache.get("k") is None


def test_size_limit_evicts_oldest():
    cache = TTLCache(60, 2)
    for i in range(3):
        cache.set(i, i)
    assert cache.get(0) is None and cache.get(2) == 2 and len(cache) == 2
