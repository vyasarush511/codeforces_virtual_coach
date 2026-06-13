from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def problem_key(problem: dict[str, Any]) -> str | None:
    contest_id = problem.get("contestId")
    index = problem.get("index")
    if contest_id is None or index is None:
        return None
    return f"{contest_id}{index}"


def utc_date(timestamp_seconds: int) -> str:
    return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).date().isoformat()


def utc_month(timestamp_seconds: int) -> str:
    return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).strftime("%Y-%m")


def build_user_profile(
    user: dict[str, Any],
    submissions: list[dict[str, Any]],
    rating_history: list[dict[str, Any]],
) -> dict[str, Any]:
    problem_attempts: dict[str, dict[str, Any]] = {}
    solved_problem_keys: set[str] = set()
    accepted_submissions = 0
    rejected_submissions = 0
    active_dates: set[str] = set()
    solved_dates: set[str] = set()
    timeline: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"month": "", "accepted": 0, "rejected": 0, "unique_solved": set()}
    )
    language_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for submission in submissions:
        problem = submission.get("problem", {})
        key = problem_key(problem)
        if not key:
            continue

        created_at = submission.get("creationTimeSeconds", 0)
        active_dates.add(utc_date(created_at))
        month = utc_month(created_at)
        timeline[month]["month"] = month
        verdict = submission.get("verdict", "UNKNOWN")
        language = submission.get("programmingLanguage", "Unknown")
        language_counts[language]["submissions"] += 1

        accepted = verdict == "OK"
        if accepted:
            accepted_submissions += 1
            language_counts[language]["accepted"] += 1
            solved_problem_keys.add(key)
            solved_dates.add(utc_date(created_at))
            timeline[month]["accepted"] += 1
            timeline[month]["unique_solved"].add(key)
        else:
            rejected_submissions += 1
            timeline[month]["rejected"] += 1

        attempt = problem_attempts.setdefault(
            key,
            {
                "key": key,
                "problem": problem,
                "accepted": False,
                "attempts": 0,
                "wrong_attempts": 0,
                "first_accepted_at": None,
                "latest_submission_at": created_at,
            },
        )
        attempt["attempts"] += 1
        attempt["latest_submission_at"] = max(attempt["latest_submission_at"], created_at)
        if accepted:
            attempt["accepted"] = True
            if attempt["first_accepted_at"] is None:
                attempt["first_accepted_at"] = created_at
        else:
            attempt["wrong_attempts"] += 1

    topic_stats = _build_topic_stats(problem_attempts, _infer_rating(user, submissions, rating_history))
    solved_ratings = [
        int(attempt["problem"]["rating"])
        for attempt in problem_attempts.values()
        if attempt["accepted"] and attempt["problem"].get("rating") is not None
    ]

    weak_tags = [
        stat["tag"]
        for stat in sorted(topic_stats, key=lambda item: item["weakness_score"], reverse=True)
        if stat["level"] in {"weak", "unexplored"}
    ][:6]
    strong_tags = [
        stat["tag"]
        for stat in sorted(topic_stats, key=lambda item: item["acceptance_rate"], reverse=True)
        if stat["level"] == "strong"
    ][:6]

    timeline_points = []
    for month in sorted(timeline):
        point = timeline[month]
        timeline_points.append(
            {
                "month": month,
                "accepted": point["accepted"],
                "rejected": point["rejected"],
                "unique_solved": len(point["unique_solved"]),
            }
        )

    languages = []
    for language, counts in language_counts.items():
        submissions_count = counts["submissions"]
        accepted_count = counts["accepted"]
        languages.append(
            {
                "language": language,
                "submissions": submissions_count,
                "accepted": accepted_count,
                "acceptance_rate": round(accepted_count / submissions_count, 4) if submissions_count else 0,
            }
        )
    languages.sort(key=lambda item: item["submissions"], reverse=True)

    inferred_rating = _infer_rating(user, submissions, rating_history)
    summary = {
        "solved_count": len(solved_problem_keys),
        "attempted_count": len(problem_attempts),
        "accepted_submissions": accepted_submissions,
        "rejected_submissions": rejected_submissions,
        "active_days": len(active_dates),
        "best_solved_rating": max(solved_ratings) if solved_ratings else None,
        "avg_solved_rating": round(mean(solved_ratings), 1) if solved_ratings else None,
        "current_streak_days": _current_streak(solved_dates),
        "max_streak_days": _max_streak(solved_dates),
        "inferred_rating": inferred_rating,
        "strong_tags": strong_tags,
        "weak_tags": weak_tags,
    }

    return {
        "summary": summary,
        "topic_stats": topic_stats,
        "languages": languages[:10],
        "timeline": timeline_points[-18:],
        "solved_problem_keys": solved_problem_keys,
        "attempted_problem_keys": set(problem_attempts),
        "problem_attempts": problem_attempts,
    }


def _build_topic_stats(problem_attempts: dict[str, dict[str, Any]], inferred_rating: int) -> list[dict[str, Any]]:
    topic: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempted_keys": set(),
            "solved_keys": set(),
            "wrong_attempts": 0,
            "solved_ratings": [],
            "latest_solve_at": None,
        }
    )

    for key, attempt in problem_attempts.items():
        problem = attempt["problem"]
        tags = problem.get("tags") or ["untagged"]
        for tag in tags:
            stat = topic[tag]
            stat["attempted_keys"].add(key)
            stat["wrong_attempts"] += attempt["wrong_attempts"]
            if attempt["accepted"]:
                stat["solved_keys"].add(key)
                if problem.get("rating") is not None:
                    stat["solved_ratings"].append(int(problem["rating"]))
                accepted_at = attempt.get("first_accepted_at")
                if accepted_at and (stat["latest_solve_at"] is None or accepted_at > stat["latest_solve_at"]):
                    stat["latest_solve_at"] = accepted_at

    rows: list[dict[str, Any]] = []
    for tag, raw in topic.items():
        attempted = len(raw["attempted_keys"])
        solved = len(raw["solved_keys"])
        wrong_attempts = raw["wrong_attempts"]
        acceptance_rate = solved / attempted if attempted else 0.0
        avg_rating = mean(raw["solved_ratings"]) if raw["solved_ratings"] else None
        max_rating = max(raw["solved_ratings"]) if raw["solved_ratings"] else None
        confidence = clamp(math.log1p(attempted) / math.log1p(30))
        weakness = _weakness_score(
            attempted=attempted,
            solved=solved,
            wrong_attempts=wrong_attempts,
            acceptance_rate=acceptance_rate,
            avg_solved_rating=avg_rating,
            inferred_rating=inferred_rating,
            confidence=confidence,
        )
        level = _topic_level(
            attempted=attempted,
            solved=solved,
            acceptance_rate=acceptance_rate,
            avg_rating=avg_rating,
            inferred_rating=inferred_rating,
            weakness=weakness,
        )
        rows.append(
            {
                "tag": tag,
                "attempted": attempted,
                "solved": solved,
                "wrong_attempts": wrong_attempts,
                "acceptance_rate": round(acceptance_rate, 4),
                "avg_solved_rating": round(avg_rating, 1) if avg_rating is not None else None,
                "max_solved_rating": max_rating,
                "latest_solve_at": utc_date(raw["latest_solve_at"]) if raw["latest_solve_at"] else None,
                "weakness_score": round(weakness, 4),
                "confidence": round(confidence, 4),
                "level": level,
            }
        )

    rows.sort(key=lambda item: (item["weakness_score"], item["attempted"]), reverse=True)
    return rows


def _weakness_score(
    attempted: int,
    solved: int,
    wrong_attempts: int,
    acceptance_rate: float,
    avg_solved_rating: float | None,
    inferred_rating: int,
    confidence: float,
) -> float:
    low_accuracy = 1 - acceptance_rate
    low_volume = 1 / math.sqrt(attempted + 1)
    rating_gap = 0.65
    if avg_solved_rating is not None:
        rating_gap = clamp((inferred_rating + 150 - avg_solved_rating) / 900)
    wrong_pressure = clamp(wrong_attempts / max(3, attempted * 3))
    no_solve_penalty = 0.2 if attempted >= 3 and solved == 0 else 0.0
    raw = (
        0.34 * low_accuracy
        + 0.24 * rating_gap
        + 0.18 * low_volume
        + 0.16 * wrong_pressure
        + no_solve_penalty
    )
    confidence_adjusted = raw * (0.58 + 0.42 * confidence)
    return clamp(confidence_adjusted)


def _topic_level(
    attempted: int,
    solved: int,
    acceptance_rate: float,
    avg_rating: float | None,
    inferred_rating: int,
    weakness: float,
) -> str:
    if attempted <= 2:
        return "unexplored"
    if solved >= 8 and acceptance_rate >= 0.68 and (avg_rating or 0) >= inferred_rating - 250:
        return "strong"
    if weakness >= 0.52:
        return "weak"
    return "developing"


def _infer_rating(
    user: dict[str, Any],
    submissions: list[dict[str, Any]],
    rating_history: list[dict[str, Any]],
) -> int:
    if user.get("rating"):
        return int(user["rating"])
    if rating_history:
        return int(rating_history[-1]["newRating"])
    solved_ratings = [
        int(submission["problem"]["rating"])
        for submission in submissions
        if submission.get("verdict") == "OK" and submission.get("problem", {}).get("rating") is not None
    ]
    if solved_ratings:
        return int(round(mean(solved_ratings) + 200, -2))
    return 1200


def _max_streak(dates: set[str]) -> int:
    if not dates:
        return 0
    parsed = sorted(datetime.fromisoformat(day).date() for day in dates)
    best = current = 1
    for previous, current_day in zip(parsed, parsed[1:]):
        if (current_day - previous).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _current_streak(dates: set[str]) -> int:
    if not dates:
        return 0
    parsed = sorted(datetime.fromisoformat(day).date() for day in dates)
    streak = 1
    for previous, current_day in zip(reversed(parsed[:-1]), reversed(parsed[1:])):
        if (current_day - previous).days == 1:
            streak += 1
        else:
            break
    return streak


def normalize_rating_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "contest_id": item["contestId"],
            "contest_name": item["contestName"],
            "rank": item["rank"],
            "old_rating": item["oldRating"],
            "new_rating": item["newRating"],
            "rating_update_time_seconds": item["ratingUpdateTimeSeconds"],
        }
        for item in history[-30:]
    ]


def normalize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": user.get("handle", ""),
        "rating": user.get("rating"),
        "rank": user.get("rank"),
        "max_rating": user.get("maxRating"),
        "max_rank": user.get("maxRank"),
        "contribution": user.get("contribution"),
        "friend_of_count": user.get("friendOfCount"),
        "avatar": user.get("avatar"),
        "title_photo": user.get("titlePhoto"),
    }

