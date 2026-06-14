from backend.evaluator import evaluate_growth_backtest, evaluate_recommender
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


def test_growth_backtest_returns_outcome_proxy_metrics():
    user = {"handle": "alice", "rating": 1300}
    submissions = [
        submission(100 + i, "A", 1200 + (i % 4) * 100, ["dp"] if i % 2 else ["graphs"], "OK", 1_700_000_000 + i * 86_400)
        for i in range(45)
    ]
    rating_history = [
        {
            "contestId": i,
            "contestName": f"Round {i}",
            "rank": 1000,
            "oldRating": 1200 + i * 10,
            "newRating": 1210 + i * 10,
            "ratingUpdateTimeSeconds": 1_700_000_000 + i * 7 * 86_400,
        }
        for i in range(8)
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
        for i in range(55)
    ]

    growth = evaluate_growth_backtest(user, submissions, rating_history, catalog, window_days=30)

    assert growth["status"] == "ok"
    assert growth["windows_evaluated"] > 0
    assert growth["avg_focus_adherence"] is not None
    assert "estimated_rating_uplift" in growth
