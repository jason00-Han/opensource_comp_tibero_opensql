from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from packages.core.database import connect, database_dsn


class MinIOTierManager:
    """Physically moves objects between separate MinIO buckets."""

    def __init__(self, client=None) -> None:
        if client is None:
            import boto3
            client = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
                region_name=os.getenv("S3_REGION", "us-east-1"))
        self.client = client
        prefix = os.getenv("S3_BUCKET", "tibero-documents")
        self.buckets = {
            "hot": os.getenv("S3_HOT_BUCKET", prefix),
            "warm": os.getenv("S3_WARM_BUCKET", f"{prefix}-warm"),
            "cold": os.getenv("S3_COLD_BUCKET", f"{prefix}-cold"),
        }
        for bucket in self.buckets.values():
            try:
                self.client.head_bucket(Bucket=bucket)
            except Exception:
                self.client.create_bucket(Bucket=bucket)

    def move(self, key: str, source: str, target: str) -> None:
        if source == target:
            return
        self.client.copy_object(Bucket=self.buckets[target], Key=key,
                                CopySource={"Bucket": self.buckets[source], "Key": key},
                                MetadataDirective="COPY")
        self.client.head_object(Bucket=self.buckets[target], Key=key)  # verify before delete
        self.client.delete_object(Bucket=self.buckets[source], Key=key)

    def transition_due(self, now: datetime | None = None) -> dict[str, int]:
        dsn = database_dsn()
        if not dsn:
            raise RuntimeError("TIBERO_DOC_DSN is required")
        now = now or datetime.now(UTC)
        warm_days = int(os.getenv("LIFECYCLE_WARM_DAYS", "30"))
        cold_days = int(os.getenv("LIFECYCLE_COLD_DAYS", "90"))
        counts = {"warm": 0, "cold": 0}
        with connect(dsn) as connection:
            rows = connection.execute("""SELECT object_key,storage_tier,last_accessed_at
                FROM tibero_doc.object_lifecycle WHERE storage_tier <> 'cold' FOR UPDATE SKIP LOCKED""").fetchall()
            for key, current, accessed in rows:
                target = ("cold" if accessed <= now - timedelta(days=cold_days)
                          else "warm" if current == "hot" and accessed <= now - timedelta(days=warm_days)
                          else current)
                if target != current:
                    self.move(key, current, target)
                    connection.execute("UPDATE tibero_doc.object_lifecycle SET storage_tier=%s,transitioned_at=now() WHERE object_key=%s",
                                       (target, key))
                    counts[target] += 1
        return counts
