from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

import fcntl
from docx import Document as DocxDocument
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".html", ".htm"}
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


@dataclass(frozen=True)
class Chunk:
    document_id: str
    filename: str
    chunk_index: int
    content: str


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    filename: str
    checksum: str
    size: int
    chunk_count: int


@dataclass(frozen=True)
class StoredDocument:
    document_id: str
    filename: str
    checksum: str
    size: int
    path: str


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    elif suffix == ".docx":
        document = DocxDocument(path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    elif suffix in {".html", ".htm"}:
        parser = _HTMLTextExtractor()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        text = "\n".join(parser.parts)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix or '(확장자 없음)'}")

    normalized = _normalize_text(text)
    if not normalized:
        raise ValueError("문서에서 텍스트를 추출하지 못했습니다.")
    return normalized


def split_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> Iterable[str]:
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)


class DocumentStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        configured = os.getenv("TIBERO_DOC_DATA_DIR")
        self.data_dir = data_dir or (Path(configured) if configured else Path.home() / ".tibero-doc" / "data")
        self.upload_dir = self.data_dir / "uploads"
        self.index_file = self.data_dir / "index.json"
        self.index_lock_file = self.data_dir / "index.lock"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _index_lock(self):
        with self.index_lock_file.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _load(self) -> dict:
        if not self.index_file.exists():
            return {"documents": [], "chunks": []}
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"인덱스를 읽을 수 없습니다: {exc}") from exc

    def _save(self, index: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(dir=self.data_dir, prefix="index-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(index, temporary, ensure_ascii=False, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
            Path(temporary_name).replace(self.index_file)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def save_upload(self, filename: str, content: bytes) -> StoredDocument:
        """Validate and persist an upload without performing expensive indexing."""
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"지원하지 않는 파일 형식입니다: {suffix or '(확장자 없음)'}")
        if not content:
            raise ValueError("빈 파일은 업로드할 수 없습니다.")

        checksum = hashlib.sha256(content).hexdigest()
        target = self.upload_dir / safe_name
        target.write_bytes(content)
        return StoredDocument(checksum[:16], safe_name, checksum, len(content), str(target))

    def ingest_bytes(self, filename: str, content: bytes) -> DocumentRecord:
        stored = self.save_upload(filename, content)
        target = Path(stored.path)
        try:
            return self._index_file(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def index_upload(self, filename: str) -> DocumentRecord:
        path = self.upload_dir / Path(filename).name
        if not path.is_file():
            raise ValueError(f"업로드 파일을 찾을 수 없습니다: {filename}")
        return self._index_file(path)

    def _index_file(self, path: Path) -> DocumentRecord:
        with self._index_lock():
            return self._index_file_unlocked(path)

    def _index_file_unlocked(self, path: Path) -> DocumentRecord:
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        document_id = checksum[:16]
        chunks = [
            Chunk(document_id, path.name, position, text)
            for position, text in enumerate(split_text(extract_text(path)))
        ]
        record = DocumentRecord(document_id, path.name, checksum, len(content), len(chunks))

        index = self._load()
        index["documents"] = [item for item in index["documents"] if item["filename"] != path.name]
        index["chunks"] = [item for item in index["chunks"] if item["filename"] != path.name]
        index["documents"].append(asdict(record))
        index["chunks"].extend(asdict(chunk) for chunk in chunks)
        self._save(index)
        return record

    def search(self, query: str, top_k: int) -> list[dict]:
        terms = TOKEN_PATTERN.findall(query.lower())
        if not terms:
            return []

        results: list[dict] = []
        for chunk in self._load()["chunks"]:
            content = chunk["content"]
            lowered = content.lower()
            matches = sum(lowered.count(term) for term in terms)
            if matches == 0:
                continue
            coverage = sum(1 for term in set(terms) if term in lowered) / len(set(terms))
            density = matches / max(len(TOKEN_PATTERN.findall(lowered)), 1)
            score = min(1.0, coverage * 0.8 + density * 0.2)
            results.append({
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "chunk_index": chunk["chunk_index"],
                "content": content,
                "score": round(score, 6),
            })
        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]

    def chunks_for_document(self, document_id: str) -> list[dict]:
        return [chunk for chunk in self._load()["chunks"] if chunk["document_id"] == document_id]

    def sync(self) -> dict[str, int]:
        with self._index_lock():
            return self._sync_unlocked()

    def _sync_unlocked(self) -> dict[str, int]:
        index = self._load()
        known = {item["filename"]: item for item in index["documents"]}
        current = {
            path.name: path
            for path in self.upload_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        }
        added = updated = skipped = 0
        for filename, path in current.items():
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            previous = known.get(filename)
            if previous is None:
                self._index_file_unlocked(path)
                added += 1
            elif previous["checksum"] != checksum:
                self._index_file_unlocked(path)
                updated += 1
            else:
                skipped += 1

        deleted_names = set(known) - set(current)
        if deleted_names:
            index = self._load()
            index["documents"] = [item for item in index["documents"] if item["filename"] not in deleted_names]
            index["chunks"] = [item for item in index["chunks"] if item["filename"] not in deleted_names]
            self._save(index)

        return {"added": added, "updated": updated, "deleted": len(deleted_names), "skipped": skipped}

    def stats(self) -> dict[str, int]:
        index = self._load()
        return {"documents": len(index["documents"]), "chunks": len(index["chunks"])}
