from __future__ import annotations

import os
from pathlib import Path


class ObjectStorage:
    def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def download_url(self, key: str, expires: int = 300) -> str | None: return None


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.getenv("TIBERO_DOC_OBJECT_DIR", Path.home() / ".tibero-doc" / "objects"))

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid object key")
        return path

    def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3ObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        import boto3
        self.bucket = os.getenv("S3_BUCKET", "tibero-documents")
        self.read_buckets = [self.bucket, os.getenv("S3_WARM_BUCKET", f"{self.bucket}-warm"),
                             os.getenv("S3_COLD_BUCKET", f"{self.bucket}-cold")]
        self.client = boto3.client(
            "s3", endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
            region_name=os.getenv("S3_REGION", "us-east-1"),
        )
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type, ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        for bucket in self.read_buckets:
            try:
                return self.client.get_object(Bucket=bucket, Key=key)["Body"].read()
            except self.client.exceptions.NoSuchKey:
                continue
            except Exception as exc:
                if "NoSuchKey" not in str(exc) and "404" not in str(exc):
                    raise
        raise FileNotFoundError(key)

    def delete(self, key: str) -> None:
        for bucket in self.read_buckets:
            self.client.delete_object(Bucket=bucket, Key=key)

    def download_url(self, key: str, expires: int = 300) -> str:
        if not hasattr(self.client, "head_object"):
            return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires)
        for bucket in self.read_buckets:
            try:
                self.client.head_object(Bucket=bucket, Key=key)
                return self.client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires)
            except Exception:
                continue
        raise FileNotFoundError(key)


def object_storage_from_env() -> ObjectStorage:
    return S3ObjectStorage() if os.getenv("OBJECT_STORAGE", "local").lower() in {"s3", "minio"} else LocalObjectStorage()
