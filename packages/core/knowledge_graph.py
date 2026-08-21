from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from itertools import combinations
from typing import Protocol

from psycopg.types.json import Jsonb

from packages.core.database import connect, database_dsn


ENTITY_SUFFIXES = {
    "organization": ("회사", "기관", "공사", "공단", "부", "청", "팀", "센터", "연구소"),
    "system": ("시스템", "플랫폼", "DB", "DBMS", "서버", "클러스터"),
    "policy": ("정책", "규정", "지침", "법", "표준"),
    "project": ("프로젝트", "사업", "과제"),
}
STOP_WORDS = {"그리고", "하지만", "관련", "문서", "내용", "대한", "위한", "통해", "에서", "으로", "합니다", "있습니다"}

ENGLISH_STOP_WORDS = {
    "and", "are", "for", "from", "into", "not", "that", "the", "this", "was", "were", "with",
}


@dataclass(frozen=True)
class EntityMention:
    entity_type: str
    name: str
    chunk_index: int
    confidence: float = 0.8
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EntityRelationship:
    source: tuple[str, str]
    target: tuple[str, str]
    relationship_type: str
    chunk_index: int
    confidence: float = 0.5


class EntityExtractor(Protocol):
    def extract(self, chunks: list[dict]) -> tuple[list[EntityMention], list[EntityRelationship]]: ...


class RuleBasedEntityExtractor:
    """외부 모델 없이도 동작하는 교체 가능한 기본 엔티티 추출기."""

    person_pattern = re.compile(r"(?<![가-힣])([가-힣]{2,4})\s*(대표|사장|팀장|담당자|연구원|개발자)[은는이가을를]?(?![가-힣])")
    token_pattern = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{2,}|[가-힣]{2,20}(?:시스템|플랫폼|프로젝트|사업|정책|규정|지침|기관|회사|공사|공단|센터|연구소|DBMS|DB)")

    def __init__(self, max_entities_per_chunk: int | None = None) -> None:
        # 관계 수는 청크 내 엔티티 수의 제곱에 비례하므로 안전한 상한을 둔다.
        self.max_entities_per_chunk = max_entities_per_chunk or int(
            os.getenv("KNOWLEDGE_GRAPH_MAX_ENTITIES_PER_CHUNK", "20")
        )

    @staticmethod
    def _classify(token: str) -> str:
        for entity_type, suffixes in ENTITY_SUFFIXES.items():
            if token.endswith(suffixes):
                return entity_type
        if re.search(r"[A-Z]", token) or any(char.isdigit() for char in token):
            return "system"
        return "topic"

    @staticmethod
    def _relationship_type(text: str) -> tuple[str, float]:
        for pattern, relation in (
            (r"사용|활용|도입", "uses"),
            (r"참조|인용|근거", "references"),
            (r"소속|포함", "belongs_to"),
            (r"관리|운영", "manages"),
            (r"대체|후속", "supersedes"),
        ):
            if re.search(pattern, text):
                return relation, 0.7
        return "co_occurs_with", 0.5

    def extract(self, chunks: list[dict]) -> tuple[list[EntityMention], list[EntityRelationship]]:
        mentions: list[EntityMention] = []
        relationships: list[EntityRelationship] = []
        seen_mentions: set[tuple[str, str, int]] = set()
        for chunk in chunks:
            index = int(chunk["chunk_index"])
            text = chunk["content"]
            current: dict[tuple[str, str], EntityMention] = {}
            for match in self.person_pattern.finditer(text):
                mention = EntityMention("person", match.group(1), index, 0.9, {"title": match.group(2)})
                current[(mention.entity_type, mention.name)] = mention
            for token in self.token_pattern.findall(text):
                name = token.strip(".,:;()[]{}\"'")
                if name in STOP_WORDS or name.lower() in ENGLISH_STOP_WORDS or len(name) < 2:
                    continue
                mention = EntityMention(self._classify(name), name, index)
                current[(mention.entity_type, mention.name)] = mention
            current = dict(list(current.items())[: self.max_entities_per_chunk])
            for key, mention in current.items():
                dedupe = (*key, index)
                if dedupe not in seen_mentions:
                    mentions.append(mention)
                    seen_mentions.add(dedupe)
            relation_type, relation_confidence = self._relationship_type(text)
            for source, target in combinations(sorted(current), 2):
                relationships.append(EntityRelationship(source, target, relation_type, index, relation_confidence))
        return mentions, relationships


def query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{1,}|[가-힣]{2,}", query)
    terms = []
    for term in raw_terms:
        normalized = re.sub(r"(에서|에게|으로|와|과|은|는|이|가|을|를)$", "", term)
        if normalized and normalized not in STOP_WORDS and normalized.lower() not in ENGLISH_STOP_WORDS and len(normalized) >= 2:
            terms.append(normalized)
    return list(dict.fromkeys(terms))[:12]


class KnowledgeGraphService:
    def __init__(self, dsn: str | None = None, extractor: EntityExtractor | None = None) -> None:
        self.dsn = dsn or database_dsn()
        self.extractor = extractor or RuleBasedEntityExtractor()

    def index_document(self, workspace_id: str, document_id: str, chunks: list[dict]) -> dict:
        if not self.dsn:
            return {"entities": 0, "relationships": 0, "provider": "disabled"}
        mentions, relationships = self.extractor.extract(chunks)
        entity_ids: dict[tuple[str, str], str] = {}
        with connect(self.dsn) as connection:
            connection.execute("DELETE FROM tibero_doc.relationships WHERE document_id=%s", (document_id,))
            connection.execute("DELETE FROM tibero_doc.document_entities WHERE document_id=%s", (document_id,))
            for mention in mentions:
                row = connection.execute(
                    """INSERT INTO tibero_doc.entities (workspace_id, entity_type, name, metadata)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (workspace_id, entity_type, name)
                       DO UPDATE SET metadata=tibero_doc.entities.metadata || EXCLUDED.metadata, updated_at=now()
                       RETURNING entity_id""",
                    (workspace_id, mention.entity_type, mention.name, Jsonb(mention.metadata)),
                ).fetchone()
                entity_id = str(row[0])
                entity_ids[(mention.entity_type, mention.name)] = entity_id
                connection.execute(
                    """INSERT INTO tibero_doc.document_entities
                           (document_id, entity_id, chunk_index, confidence, mention)
                       VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (document_id, entity_id, mention.chunk_index, mention.confidence, mention.name),
                )
            for relation in relationships:
                source = entity_ids.get(relation.source)
                target = entity_ids.get(relation.target)
                if not source or not target or source == target:
                    continue
                connection.execute(
                    """INSERT INTO tibero_doc.relationships
                           (workspace_id, source_entity_id, target_entity_id, relationship_type,
                            confidence, document_id, chunk_index)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (workspace_id, source, target, relation.relationship_type, relation.confidence, document_id, relation.chunk_index),
                )
        return {"entities": len(entity_ids), "mentions": len(mentions), "relationships": len(relationships), "provider": "rules"}

    def document_graph(self, workspace_id: str, document_id: str) -> dict:
        if not self.dsn:
            return {"entities": [], "relationships": []}
        with connect(self.dsn) as connection:
            entities = connection.execute(
                """SELECT e.entity_id, e.entity_type, e.name, de.chunk_index, de.confidence, e.metadata
                     FROM tibero_doc.document_entities de JOIN tibero_doc.entities e USING(entity_id)
                    WHERE de.document_id=%s AND e.workspace_id=%s ORDER BY de.chunk_index, e.name""",
                (document_id, workspace_id),
            ).fetchall()
            relations = connection.execute(
                """SELECT r.relationship_id, s.name, t.name, r.relationship_type,
                          r.confidence, r.chunk_index
                     FROM tibero_doc.relationships r
                     JOIN tibero_doc.entities s ON s.entity_id=r.source_entity_id
                     JOIN tibero_doc.entities t ON t.entity_id=r.target_entity_id
                    WHERE r.document_id=%s AND r.workspace_id=%s ORDER BY r.chunk_index""",
                (document_id, workspace_id),
            ).fetchall()
        return {
            "entities": [{"entity_id": str(r[0]), "entity_type": r[1], "name": r[2], "chunk_index": r[3], "confidence": r[4], "metadata": r[5]} for r in entities],
            "relationships": [{"relationship_id": str(r[0]), "source": r[1], "target": r[2], "type": r[3], "confidence": r[4], "chunk_index": r[5]} for r in relations],
        }
