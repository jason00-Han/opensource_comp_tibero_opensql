from services.api.agent import answer_question


def test_local_agent_answers_with_citations(monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "local")
    answer, provider = answer_question("OpenSQL이 뭐야?", [{"filename": "guide.txt", "chunk_index": 0, "content": "OpenSQL은 고가용성 DBMS 플랫폼입니다."}])
    assert provider == "local-extractive"
    assert "OpenSQL" in answer
    assert "[1]" in answer


def test_agent_is_honest_when_no_document_matches():
    answer, provider = answer_question("없는 내용", [])
    assert "찾지 못했습니다" in answer
    assert provider == "local-extractive"
