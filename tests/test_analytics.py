from backend.analytics import build_user_profile


def submission(contest_id, index, rating, tags, verdict, timestamp=1_700_000_000):
    return {
        "id": contest_id * 10,
        "creationTimeSeconds": timestamp,
        "programmingLanguage": "GNU C++20",
        "verdict": verdict,
        "problem": {
            "contestId": contest_id,
            "index": index,
            "name": f"Problem {contest_id}{index}",
            "rating": rating,
            "tags": tags,
        },
    }


def test_build_user_profile_marks_low_accuracy_tag_as_weak():
    user = {"handle": "alice", "rating": 1300}
    submissions = [
        submission(1, "A", 1000, ["implementation"], "OK"),
        submission(2, "A", 1100, ["implementation"], "OK"),
        submission(3, "B", 1200, ["dp"], "WRONG_ANSWER"),
        submission(3, "B", 1200, ["dp"], "TIME_LIMIT_EXCEEDED"),
        submission(4, "C", 1300, ["dp"], "OK"),
        submission(5, "D", 1300, ["graphs"], "WRONG_ANSWER"),
        submission(6, "D", 1400, ["graphs"], "WRONG_ANSWER"),
    ]

    profile = build_user_profile(user, submissions, [])
    stats = {row["tag"]: row for row in profile["topic_stats"]}

    assert stats["dp"]["weakness_score"] > stats["implementation"]["weakness_score"]
    assert "dp" in profile["summary"]["weak_tags"]
    assert profile["summary"]["solved_count"] == 3

