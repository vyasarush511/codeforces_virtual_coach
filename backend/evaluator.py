from __future__ import annotations

import math
from statistics import mean
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


def evaluate_growth_backtest(
    user: dict[str, Any],
    submissions: list[dict[str, Any]],
    rating_history: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    window_days: int = 60,
    max_checkpoints: int = 6,
) -> dict[str, Any]:
    """Estimate whether recommendation-aligned practice correlates with growth.

    This is not a causal A/B test. It is a historical proxy: at several past
    rating checkpoints, generate the advice that would have been given then,
    measure whether the user later solved similar problems, and compare rating
    movement in high-adherence vs low-adherence windows.
    """

    if len(rating_history) < 4:
        return {
            "status": "insufficient_rating_history",
            "message": "Need at least 4 rated contests for growth backtesting.",
            "window_days": window_days,
            "windows_evaluated": 0,
            "followed_windows": 0,
            "baseline_windows": 0,
            "avg_rating_delta_followed": None,
            "avg_rating_delta_baseline": None,
            "estimated_rating_uplift": None,
            "avg_focus_adherence": None,
            "avg_weak_tag_skill_gain": None,
        }

    windows: list[dict[str, Any]] = []
    for event in _sample_checkpoints(rating_history, max_checkpoints):
        cutoff = event.get("ratingUpdateTimeSeconds", 0)
        end_time = cutoff + window_days * 24 * 60 * 60
        future_rating_events = [
            item
            for item in rating_history
            if cutoff < item.get("ratingUpdateTimeSeconds", 0) <= end_time
        ]
        if not future_rating_events:
            continue

        training_submissions = [
            submission
            for submission in submissions
            if submission.get("creationTimeSeconds", 0) <= cutoff
        ]
        future_solves = _unique_accepted_between(submissions, cutoff, end_time)
        if len(future_solves) < 3:
            continue

        training_rating = [
            item
            for item in rating_history
            if item.get("ratingUpdateTimeSeconds", 0) <= cutoff
        ]
        training_profile = build_user_profile(user, training_submissions, training_rating)
        if training_profile["summary"]["solved_count"] < 20:
            continue

        recommendations, _ = recommend_problems_with_metadata(training_profile, catalog, top_n=20)
        focus_tags = training_profile["summary"]["weak_tags"][:4] or _top_recommendation_tags(recommendations)
        if not focus_tags:
            continue

        rec_ratings = [item["rating"] for item in recommendations if item.get("rating")]
        low_rating = min(rec_ratings) - 100 if rec_ratings else max(800, event["newRating"] - 250)
        high_rating = max(rec_ratings) + 100 if rec_ratings else event["newRating"] + 500
        aligned_solves = [
            submission
            for submission in future_solves
            if _matches_focus(submission, focus_tags, low_rating, high_rating)
        ]
        adherence = len(aligned_solves) / len(future_solves)
        before_skill = _avg_solved_rating_for_tags(training_submissions, focus_tags)
        after_skill = _avg_solved_rating_for_tags(future_solves, focus_tags)
        skill_gain = None
        if before_skill is not None and after_skill is not None:
            skill_gain = after_skill - before_skill

        windows.append(
            {
                "cutoff_date": utc_date(cutoff),
                "rating_delta": future_rating_events[-1]["newRating"] - event["newRating"],
                "future_solves": len(future_solves),
                "aligned_solves": len(aligned_solves),
                "focus_adherence": adherence,
                "followed": adherence >= 0.25,
                "weak_tag_skill_gain": skill_gain,
                "focus_tags": focus_tags,
            }
        )

    if not windows:
        return {
            "status": "insufficient_windows",
            "message": "Not enough future solve/rating windows to estimate growth.",
            "window_days": window_days,
            "windows_evaluated": 0,
            "followed_windows": 0,
            "baseline_windows": 0,
            "avg_rating_delta_followed": None,
            "avg_rating_delta_baseline": None,
            "estimated_rating_uplift": None,
            "avg_focus_adherence": None,
            "avg_weak_tag_skill_gain": None,
        }

    followed = [window for window in windows if window["followed"]]
    baseline = [window for window in windows if not window["followed"]]
    followed_delta = _mean_or_none([window["rating_delta"] for window in followed])
    baseline_delta = _mean_or_none([window["rating_delta"] for window in baseline])
    uplift = None
    if followed_delta is not None and baseline_delta is not None:
        uplift = followed_delta - baseline_delta

    return {
        "status": "ok",
        "window_days": window_days,
        "windows_evaluated": len(windows),
        "followed_windows": len(followed),
        "baseline_windows": len(baseline),
        "avg_rating_delta_followed": _round_or_none(followed_delta, 1),
        "avg_rating_delta_baseline": _round_or_none(baseline_delta, 1),
        "estimated_rating_uplift": _round_or_none(uplift, 1),
        "avg_focus_adherence": _round_or_none(_mean_or_none([window["focus_adherence"] for window in windows]), 4),
        "avg_weak_tag_skill_gain": _round_or_none(
            _mean_or_none([
                window["weak_tag_skill_gain"]
                for window in windows
                if window["weak_tag_skill_gain"] is not None
            ]),
            1,
        ),
        "windows": windows,
        "note": "Growth backtest is correlational, not causal; it estimates whether recommendation-aligned practice historically coincided with stronger outcomes.",
    }


def _sample_checkpoints(rating_history: list[dict[str, Any]], max_checkpoints: int) -> list[dict[str, Any]]:
    eligible = rating_history[1:-1]
    if len(eligible) <= max_checkpoints:
        return eligible
    step = max(1, len(eligible) // max_checkpoints)
    sampled = eligible[::step][:max_checkpoints]
    return sampled


def _unique_accepted_between(
    submissions: list[dict[str, Any]],
    start_time: int,
    end_time: int,
) -> list[dict[str, Any]]:
    first_by_key: dict[str, dict[str, Any]] = {}
    for submission in submissions:
        if submission.get("verdict") != "OK":
            continue
        created_at = submission.get("creationTimeSeconds", 0)
        if not (start_time < created_at <= end_time):
            continue
        key = problem_key(submission.get("problem", {}))
        if not key:
            continue
        current = first_by_key.get(key)
        if current is None or created_at < current.get("creationTimeSeconds", 0):
            first_by_key[key] = submission
    return list(first_by_key.values())


def _matches_focus(
    submission: dict[str, Any],
    focus_tags: list[str],
    low_rating: int,
    high_rating: int,
) -> bool:
    problem = submission.get("problem", {})
    rating = problem.get("rating")
    if rating is None or not (low_rating <= int(rating) <= high_rating):
        return False
    return bool(set(problem.get("tags", [])).intersection(focus_tags))


def _avg_solved_rating_for_tags(
    submissions: list[dict[str, Any]],
    tags: list[str],
) -> float | None:
    tag_set = set(tags)
    ratings = [
        int(submission["problem"]["rating"])
        for submission in submissions
        if submission.get("verdict") == "OK"
        and submission.get("problem", {}).get("rating") is not None
        and tag_set.intersection(submission.get("problem", {}).get("tags", []))
    ]
    return mean(ratings) if ratings else None


def _top_recommendation_tags(recommendations: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for recommendation in recommendations[:10]:
        for tag in recommendation.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return [
        tag
        for tag, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:4]
    ]


def _mean_or_none(values: list[float | int]) -> float | None:
    return mean(values) if values else None


def _round_or_none(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None
