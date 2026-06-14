from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from .analytics import build_user_profile, normalize_rating_history, normalize_user
from .cf_client import CodeforcesAPIError, CodeforcesClient
from .config import get_settings
from .evaluator import evaluate_recommender
from .planner import build_training_plan
from .recommender import build_problem_catalog, recommend_problems_with_metadata


async def analyze_handle(handle: str, limit: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
    settings = get_settings()
    count = min(limit or settings.max_submissions, settings.max_submissions)

    async with CodeforcesClient(settings=settings) as client:
        user_info_task = client.user_info(handle, force_refresh=force_refresh)
        submissions_task = client.user_status(handle, count=count, force_refresh=force_refresh)
        rating_task = client.user_rating(handle, force_refresh=force_refresh)
        problemset_task = client.problemset(force_refresh=force_refresh)
        user_info, submissions, rating_history, problemset_payload = await asyncio.gather(
            user_info_task,
            submissions_task,
            rating_task,
            problemset_task,
        )
        cache_stats = client.cache.stats()

    if not user_info:
        raise CodeforcesAPIError(f"Handle '{handle}' was not found")

    user = user_info[0]
    profile = build_user_profile(user, submissions, rating_history)
    catalog = build_problem_catalog(problemset_payload)
    recommendations, recommender_model = recommend_problems_with_metadata(
        profile,
        catalog,
        top_n=settings.default_recommendations,
    )
    evaluation = evaluate_recommender(user, submissions, rating_history, catalog, k=10)
    plan = build_training_plan(profile, recommendations)

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "Codeforces API",
        "user": normalize_user(user),
        "profile": profile["summary"],
        "topic_stats": profile["topic_stats"][:18],
        "languages": profile["languages"],
        "timeline": profile["timeline"],
        "rating_history": normalize_rating_history(rating_history),
        "recommender_model": recommender_model,
        "evaluation": evaluation,
        "recommendations": recommendations,
        "plan": plan,
        "cache": {
            **cache_stats,
            "problem_catalog_size": len(catalog),
            "submissions_loaded": len(submissions),
        },
    }
