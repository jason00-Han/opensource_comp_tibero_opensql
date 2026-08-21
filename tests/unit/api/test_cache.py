import json

from services.api.cache import PopularDocumentCache


class FakeRedis:
    def __init__(self): self.values = {}; self.scores = {}
    def zincrby(self, key, amount, member): self.scores[(key, member)] = self.scores.get((key, member), 0) + amount; return self.scores[(key, member)]
    def setex(self, key, ttl, value): self.values[key] = value
    def get(self, key): return self.values.get(key)
    def delete(self, key): self.values.pop(key, None)
    def ping(self): return True


def test_document_is_cached_only_after_popularity_threshold(monkeypatch):
    cache = PopularDocumentCache(); cache.threshold = 2
    redis = FakeRedis(); monkeypatch.setattr(cache, "_client", lambda: redis)
    value = {"document_id": "doc-1", "chunks": []}
    assert cache.record_and_cache("ws", "doc-1", value) == 1
    assert cache.get("ws", "doc-1") is None
    assert cache.record_and_cache("ws", "doc-1", value) == 2
    assert cache.get("ws", "doc-1") == value
    cache.invalidate("ws", "doc-1")
    assert cache.get("ws", "doc-1") is None
