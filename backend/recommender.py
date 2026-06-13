from __future__ import annotations

import math
from typing import Any

from .analytics import clamp, problem_key
from .content_recommender import score_content_similarity


def build_problem_catalog(problemset_payload: dict[str, Any]) -> list[dict[str, Any]]:
    stats_by_key = {}
    for stat in problemset_payload.get("problemStatistics", []):
        key = problem_key(stat)
        if key:
            stats_by_key[key] = int(stat.get("solvedCount", 0))

    catalog = []
    for problem in problemset_payload.get("problems", []):
        key = problem_key(problem)
        rating = problem.get("rating")
        if not key or rating is None:
            continue
        contest_id = problem.get("contestId")
        index = problem.get("index")
        catalog.append(
            {
                "key": key,
                "contest_id": int(contest_id),
                "index": str(index),
                "name": problem.get("name", "Unknown problem"),
                "rating": int(rating),
                "tags": list(problem.get("tags", [])),
                "solved_count": stats_by_key.get(key, 0),
                "url": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
            }
        )
    return catalog


def recommend_problems(profile: dict[str, Any], catalog: list[dict[str, Any]], top_n: int = 24) -> list[dict[str, Any]]:
    recommendations, _ = recommend_problems_with_metadata(profile, catalog, top_n=top_n)
    return recommendations


def recommend_problems_with_metadata(
    profile: dict[str, Any],
    catalog: list[dict[str, Any]],
    top_n: int = 24,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = profile["summary"]
    user_rating = int(summary["inferred_rating"])
    solved_keys = profile["solved_problem_keys"]
    attempted_keys = profile["attempted_problem_keys"]
    weak_tags = set(summary["weak_tags"])
    topic_by_tag = {row["tag"]: row for row in profile["topic_stats"]}
    max_solved_count = max((problem["solved_count"] for problem in catalog), default=1)
    content_result = score_content_similarity(profile, catalog)

    candidates = []
    for problem in catalog:
        if problem["key"] in solved_keys:
            continue
        rating = problem["rating"]
        if not _inside_candidate_band(rating, user_rating, weak_tags, problem["tags"]):
            continue

        features = _score_features(
            problem=problem,
            user_rating=user_rating,
            attempted=problem["key"] in attempted_keys,
            weak_tags=weak_tags,
            topic_by_tag=topic_by_tag,
            max_solved_count=max_solved_count,
        )
        features["content_similarity"] = content_result.scores.get(problem["key"], 0.0)
        rule_score = (
            0.40 * features["tag_weakness"]
            + 0.28 * features["difficulty_fit"]
            + 0.16 * features["popularity"]
            + 0.10 * features["undertrained_tag"]
            + 0.06 * features["retry_value"]
        )
        features["rule_score"] = rule_score
        score = (
            0.58 * rule_score
            + 0.34 * features["content_similarity"]
            + 0.08 * features["freshness"]
        )
        candidates.append(
            {
                **{k: v for k, v in problem.items() if k != "key"},
                "key": problem["key"],
                "score": round(score, 4),
                "difficulty_fit": round(features["difficulty_fit"], 4),
                "priority": _priority(problem, user_rating, weak_tags, attempted=problem["key"] in attempted_keys),
                "why": _explain(
                    problem,
                    user_rating,
                    weak_tags,
                    topic_by_tag,
                    attempted=problem["key"] in attempted_keys,
                    content_similarity=features["content_similarity"],
                ),
                "features": {k: round(v, 4) for k, v in features.items()},
            }
        )

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)[:300]
    selected = _diversify(ranked, top_n=top_n)
    for item in selected:
        item.pop("key", None)
    return selected, content_result.metadata


def _inside_candidate_band(rating: int, user_rating: int, weak_tags: set[str], problem_tags: list[str]) -> bool:
    low = max(800, user_rating - 250)
    high = user_rating + 500
    if low <= rating <= high:
        return True
    if weak_tags.intersection(problem_tags) and low <= rating <= high + 150:
        return True
    return False


def _score_features(
    problem: dict[str, Any],
    user_rating: int,
    attempted: bool,
    weak_tags: set[str],
    topic_by_tag: dict[str, dict[str, Any]],
    max_solved_count: int,
) -> dict[str, float]:
    tags = problem["tags"]
    tag_weakness_values = [topic_by_tag.get(tag, {}).get("weakness_score", 0.32) for tag in tags]
    tag_weakness = max(tag_weakness_values) if tag_weakness_values else 0.2
    weak_overlap = len(weak_tags.intersection(tags)) / max(1, len(tags))
    undertrained_values = [
        1 - min(1.0, topic_by_tag.get(tag, {}).get("attempted", 0) / 12)
        for tag in tags
    ]
    undertrained_tag = max(undertrained_values) if undertrained_values else 0.25
    difficulty_fit = _difficulty_fit(problem["rating"], user_rating)
    popularity = math.log1p(problem["solved_count"]) / math.log1p(max_solved_count or 1)
    freshness = _freshness_proxy(problem["contest_id"])
    retry_value = 1.0 if attempted else 0.0
    return {
        "tag_weakness": clamp(0.75 * tag_weakness + 0.25 * weak_overlap),
        "difficulty_fit": difficulty_fit,
        "popularity": clamp(popularity),
        "undertrained_tag": clamp(undertrained_tag),
        "retry_value": retry_value,
        "freshness": freshness,
    }


def _difficulty_fit(problem_rating: int, user_rating: int) -> float:
    target = user_rating + 125
    sigma = 285
    return clamp(math.exp(-((problem_rating - target) ** 2) / (2 * sigma * sigma)))


def _freshness_proxy(contest_id: int) -> float:
    # Contest ids grow over time; this normalized proxy rewards not-too-old problems
    # without needing a separate contest metadata request.
    return clamp((contest_id - 900) / 1400)


def _priority(problem: dict[str, Any], user_rating: int, weak_tags: set[str], attempted: bool) -> str:
    if attempted:
        return "Repair"
    if problem["rating"] >= user_rating + 300:
        return "Stretch"
    if weak_tags.intersection(problem["tags"]):
        return "Core"
    return "Explore"


def _explain(
    problem: dict[str, Any],
    user_rating: int,
    weak_tags: set[str],
    topic_by_tag: dict[str, dict[str, Any]],
    attempted: bool,
    content_similarity: float,
) -> list[str]:
    reasons: list[str] = []
    overlap = weak_tags.intersection(problem["tags"])
    if overlap:
        tag = sorted(overlap, key=lambda item: topic_by_tag.get(item, {}).get("weakness_score", 0), reverse=True)[0]
        stat = topic_by_tag.get(tag, {})
        reasons.append(
            f"Targets {tag}: {int(stat.get('acceptance_rate', 0) * 100)}% solve rate across attempted problems"
        )
    if attempted:
        reasons.append("Already attempted but not solved, making it a high-value repair problem")
    gap = problem["rating"] - user_rating
    if -100 <= gap <= 250:
        reasons.append("Sits in the optimal growth band for your current rating")
    elif gap > 250:
        reasons.append("Stretch problem for rating-upside practice")
    if content_similarity >= 0.68:
        reasons.append("High content match to your weakness vector")
    if problem["solved_count"] >= 1000:
        reasons.append("Popular enough to have reliable editorials and community discussion")
    return reasons[:3] or ["Balances difficulty, tag coverage, and problem quality"]


def _diversify(candidates: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    remaining = candidates[:]
    while remaining and len(selected) < top_n:
        best_index = 0
        best_score = -1.0
        for index, candidate in enumerate(remaining):
            penalty = _diversity_penalty(candidate, selected)
            adjusted = candidate["score"] - penalty
            if adjusted > best_score:
                best_score = adjusted
                best_index = index
        selected.append(remaining.pop(best_index))
    return selected


def _diversity_penalty(candidate: dict[str, Any], selected: list[dict[str, Any]]) -> float:
    if not selected:
        return 0.0
    candidate_tags = set(candidate["tags"])
    tag_penalty = 0.0
    rating_penalty = 0.0
    for item in selected:
        other_tags = set(item["tags"])
        if candidate_tags and other_tags:
            tag_penalty = max(tag_penalty, len(candidate_tags.intersection(other_tags)) / len(candidate_tags.union(other_tags)))
        if abs(candidate["rating"] - item["rating"]) <= 100:
            rating_penalty = max(rating_penalty, 0.2)
    return 0.09 * tag_penalty + 0.03 * rating_penalty
