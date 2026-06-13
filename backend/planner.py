from __future__ import annotations

from typing import Any


def build_training_plan(profile: dict[str, Any], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    summary = profile["summary"]
    inferred_rating = int(summary["inferred_rating"])
    weak_tags = summary["weak_tags"][:4]
    next_target = _next_target(inferred_rating)

    core = [item for item in recommendations if item["priority"] in {"Core", "Repair"}]
    stretch = [item for item in recommendations if item["priority"] == "Stretch"]
    explore = [item for item in recommendations if item["priority"] == "Explore"]

    today = (core + recommendations)[:3]
    week = _unique_by_problem(core[3:] + explore + recommendations, exclude=today)[:7]
    stretch_block = _unique_by_problem(stretch + recommendations, exclude=today + week)[:3]

    focus = ", ".join(weak_tags[:3]) if weak_tags else "mixed fundamentals"
    blocks = [
        {
            "title": "Today",
            "focus": f"Repair and sharpen {focus}",
            "problems": today,
        },
        {
            "title": "This week",
            "focus": "Build volume without leaving the rating-growth band",
            "problems": week,
        },
        {
            "title": "Stretch",
            "focus": f"Probe readiness for {next_target}",
            "problems": stretch_block,
        },
    ]

    milestones = [
        f"Solve at least {max(4, len(week) // 2)} recommended problems before changing focus tags",
        f"Raise weak-tag solve rate above 60% for {weak_tags[0] if weak_tags else 'your lowest-confidence tag'}",
        f"Keep most practice in the {max(800, inferred_rating - 100)}-{next_target} band",
    ]

    return {
        "current_band": f"{(inferred_rating // 100) * 100}-{((inferred_rating // 100) + 1) * 100}",
        "next_target_rating": next_target,
        "weekly_load": len(week) + len(today),
        "focus_tags": weak_tags,
        "blocks": blocks,
        "milestones": milestones,
    }


def _next_target(rating: int) -> int:
    return ((rating // 100) + 2) * 100


def _unique_by_problem(items: list[dict[str, Any]], exclude: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    seen = {(item["contest_id"], item["index"]) for item in (exclude or [])}
    unique = []
    for item in items:
        key = (item["contest_id"], item["index"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique

