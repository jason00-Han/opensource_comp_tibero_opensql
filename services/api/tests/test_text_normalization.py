from pathlib import Path

from services.api.store import extract_pages


def test_text_extraction_removes_nul_bytes(tmp_path: Path):
    source = tmp_path / "nul.txt"
    source.write_bytes(b"Open\x00SQL document")

    assert extract_pages(source) == [(None, "OpenSQL document")]
