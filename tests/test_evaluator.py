from backend.evaluator import evaluate_recommender
from tests.test_analytics import submission


def test_temporal_evaluator_returns_ranking_metrics():
    user = {"handle": "alice", "rating": 1300}
    submissions = [
        submission(100 + i, "A", 1200 + (i % 4) * 100, ["dp"] if i % 2 else ["graphs"], "OK", 1_700_000_000 + i)
        for i in range(25)
    ]
    catalog = [
        {
            "key": f"{100 + i}A",
            "contest_id": 100 + i,
            "index": "A",
            "name": f"Problem {i}",
            "rating": 1200 + (i % 4) * 100,
            "tags": ["dp"] if i % 2 else ["graphs"],
            "solved_count": 1000 + i,
            "url": f"https://codeforces.com/problemset/problem/{100 + i}/A",
        }
        for i in range(30)
    ]

    evaluation = evaluate_recommender(user, submissions, [], catalog, k=10)

    assert evaluation["status"] == "ok"
    assert evaluation["train_solved"] == 20
    assert evaluation["holdout_solved"] == 5
    assert evaluation["precision_at_k"] is not None
    assert evaluation["hit_rate_at_k"] in {0.0, 1.0}
    assert evaluation["ndcg_at_k"] is not None
    assert evaluation["mrr"] is not None

