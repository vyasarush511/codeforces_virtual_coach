from backend.analytics import build_user_profile
from backend.recommender import build_problem_catalog, recommend_problems

from tests.test_analytics import submission


def test_recommender_filters_solved_and_prioritizes_weak_tags():
    user = {"handle": "alice", "rating": 1300}
    submissions = [
        submission(1, "A", 1000, ["implementation"], "OK"),
        submission(2, "B", 1200, ["dp"], "WRONG_ANSWER"),
        submission(3, "C", 1300, ["dp"], "OK"),
    ]
    profile = build_user_profile(user, submissions, [])
    catalog = [
        {
            "key": "1A",
            "contest_id": 1,
            "index": "A",
            "name": "Solved Already",
            "rating": 1000,
            "tags": ["implementation"],
            "solved_count": 10000,
            "url": "https://codeforces.com/problemset/problem/1/A",
        },
        {
            "key": "10D",
            "contest_id": 10,
            "index": "D",
            "name": "DP Growth",
            "rating": 1400,
            "tags": ["dp"],
            "solved_count": 5000,
            "url": "https://codeforces.com/problemset/problem/10/D",
        },
        {
            "key": "11A",
            "contest_id": 11,
            "index": "A",
            "name": "Easy Implementation",
            "rating": 900,
            "tags": ["implementation"],
            "solved_count": 20000,
            "url": "https://codeforces.com/problemset/problem/11/A",
        },
    ]

    recommendations = recommend_problems(profile, catalog, top_n=2)

    assert all(item["name"] != "Solved Already" for item in recommendations)
    assert recommendations[0]["name"] == "DP Growth"
    assert recommendations[0]["priority"] in {"Core", "Repair", "Stretch"}
    assert "content_similarity" in recommendations[0]["features"]
    assert "rule_score" in recommendations[0]["features"]


def test_problem_catalog_filters_cyrillic_problem_titles():
    payload = {
        "problems": [
            {"contestId": 1, "index": "A", "name": "English Title", "rating": 1200, "tags": ["dp"]},
            {"contestId": 2, "index": "B", "name": "Русское название", "rating": 1200, "tags": ["math"]},
        ],
        "problemStatistics": [
            {"contestId": 1, "index": "A", "solvedCount": 10},
            {"contestId": 2, "index": "B", "solvedCount": 20},
        ],
    }

    catalog = build_problem_catalog(payload)

    assert [problem["name"] for problem in catalog] == ["English Title"]
