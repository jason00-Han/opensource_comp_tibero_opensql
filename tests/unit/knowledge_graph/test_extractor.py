from packages.core.knowledge_graph import RuleBasedEntityExtractor, query_terms


def test_rule_extractor_finds_entities_and_cooccurrence():
    extractor = RuleBasedEntityExtractor()
    entities, relationships = extractor.extract([{
        "chunk_index": 0,
        "content": "김민수 팀장은 OpenSQL과 TiberoDB를 티맥스연구소 프로젝트에서 사용한다.",
    }])
    values = {(item.entity_type, item.name) for item in entities}
    assert ("person", "김민수") in values
    assert ("system", "OpenSQL") in values
    assert ("system", "TiberoDB") in values
    assert relationships
    assert all(item.relationship_type == "uses" for item in relationships)


def test_query_terms_remove_common_words_and_duplicates():
    assert query_terms("OpenSQL 관련 문서에서 OpenSQL 정책을 찾아줘") == ["OpenSQL", "정책", "찾아줘"]
