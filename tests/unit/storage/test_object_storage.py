from packages.core.object_storage import LocalObjectStorage


def test_local_object_storage_round_trip(tmp_path):
    storage = LocalObjectStorage(tmp_path)
    storage.put("workspace/checksum/report.txt", b"document", "text/plain")
    assert storage.get("workspace/checksum/report.txt") == b"document"
    storage.delete("workspace/checksum/report.txt")
    assert not (tmp_path / "workspace/checksum/report.txt").exists()
