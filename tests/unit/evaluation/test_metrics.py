from evaluation.evaluate_search import score_case


def test_search_metrics_reward_early_relevant_results():
    score = score_case(["wrong", "right", "other"], {"right"}, 3)
    assert score["recall_at_k"] == 1.0
    assert score["mrr"] == 0.5
    assert 0 < score["ndcg_at_k"] < 1
