from __future__ import annotations

import os

import httpx


def _context(results: list[dict]) -> str:
    return "\n\n".join(
        f"[{index}] {item['filename']} (chunk {item['chunk_index']})\n{item['content']}"
        for index, item in enumerate(results, 1)
    )


def answer_question(question: str, results: list[dict]) -> tuple[str, str]:
    """검색 근거만 사용한다. 키가 없으면 안전한 추출형 답변으로 동작한다."""
    if not results:
        return "관련 문서를 찾지 못했습니다. 문서를 업로드하거나 검색어를 구체화해 주세요.", "local-extractive"
    provider = os.getenv("AGENT_PROVIDER", "local").lower()
    context = _context(results)
    instruction = (
        "다음 문서 근거만 사용해 한국어로 답하세요. 근거가 부족하면 부족하다고 말하고, "
        "문장 끝에 [1] 형태로 출처 번호를 붙이세요.\n\n"
        f"질문: {question}\n\n근거:\n{context}"
    )
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        response = httpx.post(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": os.getenv("AGENT_MODEL", "gpt-4.1-mini"), "messages": [{"role": "user", "content": instruction}], "temperature": 0},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"], "openai"
    if provider == "ollama":
        response = httpx.post(
            os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate",
            json={"model": os.getenv("AGENT_MODEL", "qwen2.5:7b"), "prompt": instruction, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["response"], "ollama"
    excerpts = "\n".join(f"- {item['content'].strip()} [{i}]" for i, item in enumerate(results[:3], 1))
    return f"관련 문서에서 다음 내용을 찾았습니다.\n{excerpts}", "local-extractive"
