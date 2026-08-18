import sys
from types import SimpleNamespace

from packages.core.object_storage import S3ObjectStorage, object_storage_from_env


class FakeBody:
    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def head_bucket(self, **kwargs):
        raise RuntimeError("missing")

    def create_bucket(self, **kwargs):
        self.calls.append(("create_bucket", kwargs))

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {"Body": FakeBody(self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://signed.test/{Params['Key']}?expires={ExpiresIn}"


def test_s3_round_trip_encryption_and_signed_download(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: client))
    monkeypatch.setenv("OBJECT_STORAGE", "minio")
    monkeypatch.setenv("S3_BUCKET", "documents")

    storage = object_storage_from_env()
    assert isinstance(storage, S3ObjectStorage)
    storage.put("workspace/report.txt", b"classified", "text/plain")
    put = next(value for name, value in client.calls if name == "put_object")
    assert put["Bucket"] == "documents"
    assert put["ContentType"] == "text/plain"
    assert put["ServerSideEncryption"] == "AES256"
    assert storage.get("workspace/report.txt") == b"classified"
    assert storage.download_url("workspace/report.txt", 60).endswith("expires=60")
    storage.delete("workspace/report.txt")
    assert "workspace/report.txt" not in client.objects
