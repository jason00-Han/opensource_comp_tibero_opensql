from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


def score_case(ranked: list[str], relevant: set[str], k: int) -> dict[str, float]:
    top = ranked[:k]
    hits = [1 if item in relevant else 0 for item in top]
    recall = len(set(top) & relevant) / len(relevant) if relevant else 0.0
    rr = next((1.0 / (index + 1) for index, hit in enumerate(hits) if hit), 0.0)
    dcg = sum(hit / math.log2(index + 2) for index, hit in enumerate(hits))
    ideal = sum(1 / math.log2(index + 2) for index in range(min(len(relevant), k)))
    return {"recall_at_k": recall, "mrr": rr, "ndcg_at_k": dcg / ideal if ideal else 0.0}


def evaluate(dataset: Path, api_url: str, token: str, k: int = 5) -> dict:
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    scored = []
    for case in cases:
        request = Request(f"{api_url.rstrip('/')}/v1/search", method="POST",
            data=json.dumps({"query": case["query"], "top_k": k, "mode": "hybrid"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=60) as response:
            body = json.load(response)
        results = body.get("results", body if isinstance(body, list) else [])
        ranked = [str(item.get("document_id")) for item in results]
        scored.append({"query": case["query"], **score_case(ranked, set(case["relevant_document_ids"]), k)})
    metrics = {name: sum(row[name] for row in scored) / len(scored)
               for name in ("recall_at_k", "mrr", "ndcg_at_k")} if scored else {}
    return {"cases": len(scored), "k": k, "metrics": metrics, "details": scored}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/search_gold.jsonl"))
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("evaluation/results.json"))
    args = parser.parse_args()
    result = evaluate(args.dataset, args.api_url, args.token, args.k)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["metrics"], indent=2))
