from __future__ import annotations

import math
from typing import Any

from .analytics import build_user_profile, problem_key, utc_date
from .recommender import recommend_problems_with_metadata


def evaluate_recommender(
    user: dict[str, Any],
    submissions: list[dict[str, Any]],
    rating_history: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    k: int = 10,
) -> dict[str, Any]:
    """Temporal holdout evaluation for the current user's recommender.

    We sort unique accepted solves by first accepted time, train on the older 80%,
    recommend top-k problems, and measure whether the newer 20% appears in the
    recommendation list.
    """

    solved_events = _first_solve_events(submissions)
    if len(solved_events) < 20:
        return {
            "status": "insufficient_history",
            "k": k,
            "message": "Need at least 20 solved problems for temporal backtesting.",
            "train_solved": len(solved_events),
            "holdout_solved": 0,
            "precision_at_k": None,
            "hit_rate_at_k": None,
            "ndcg_at_k": None,
            "mrr": None,
            "hits": [],
        }

    split_index = max(1, int(len(solved_events) * 0.8))
    split_index = min(split_index, len(solved_events) - 1)
    cutoff = solved_events[split_index - 1]["accepted_at"]
    holdout_keys = {event["key"] for event in solved_events[split_index:]}
    training_submissions = [
        submission
        for submission in submissions
        if submission.get("creationTimeSeconds", 0) <= cutoff
    ]
    training_rating = [
        item
        for item in rating_history
        if item.get("ratingUpdateTimeSeconds", 0) <= cutoff
    ]
    training_profile = build_user_profile(user, training_submissions, training_rating)
    recommendations, _ = recommend_problems_with_metadata(training_profile, catalog, top_n=k)
    recommended_keys = [
        f"{item['contest_id']}{item['index']}"
        for item in recommendations[:k]
    ]
    hit_keys = [key for key in recommended_keys if key in holdout_keys]

    return {
        "status": "ok",
        "k": k,
        "cutoff_date": utc_date(cutoff),
        "train_solved": split_index,
        "holdout_solved": len(holdout_keys),
        "precision_at_k": round(len(hit_keys) / k, 4),
        "hit_rate_at_k": 1.0 if hit_keys else 0.0,
        "ndcg_at_k": round(_ndcg(recommended_keys, holdout_keys, k), 4),
        "mrr": round(_mrr(recommended_keys, holdout_keys), 4),
        "hits": hit_keys,
    }


def _first_solve_events(submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    first_by_key: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        if submission.get("verdict") != "OK":
            continue
        key = problem_key(submission.get("problem", {}))
        if not key:
            continue
        accepted_at = submission.get("creationTimeSeconds", 0)
        current = first_by_key.get(key)
        if current is None or accepted_at < current["accepted_at"]:
            first_by_key[key] = {"key": key, "accepted_at": accepted_at}
    return sorted(first_by_key.values(), key=lambda item: item["accepted_at"])


def _ndcg(recommended_keys: list[str], relevant_keys: set[str], k: int) -> float:
    dcg = 0.0
    for index, key in enumerate(recommended_keys[:k], start=1):
        if key in relevant_keys:
            dcg += 1 / math.log2(index + 1)
    ideal_hits = min(k, len(relevant_keys))
    idcg = sum(1 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def _mrr(recommended_keys: list[str], relevant_keys: set[str]) -> float:
    for index, key in enumerate(recommended_keys, start=1):
        if key in relevant_keys:
            return 1 / index
    return 0.0

