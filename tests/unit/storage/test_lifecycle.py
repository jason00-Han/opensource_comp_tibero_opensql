from datetime import UTC, datetime

from packages.core.lifecycle import MinIOTierManager


class FakeS3:
    def __init__(self): self.objects = {"hot": {"x": b"data"}, "warm": {}, "cold": {}}
    def head_bucket(self, Bucket): return None
    def create_bucket(self, Bucket): self.objects.setdefault(Bucket, {})
    def copy_object(self, Bucket, Key, CopySource, MetadataDirective):
        self.objects[Bucket][Key] = self.objects[CopySource["Bucket"]][Key]
    def head_object(self, Bucket, Key): return {"size": len(self.objects[Bucket][Key])}
    def delete_object(self, Bucket, Key): self.objects[Bucket].pop(Key)


def test_move_verifies_copy_then_deletes_source(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "hot")
    monkeypatch.setenv("S3_WARM_BUCKET", "warm")
    monkeypatch.setenv("S3_COLD_BUCKET", "cold")
    client = FakeS3()
    manager = MinIOTierManager(client)
    manager.move("x", "hot", "warm")
    assert "x" not in client.objects["hot"]
    assert client.objects["warm"]["x"] == b"data"
