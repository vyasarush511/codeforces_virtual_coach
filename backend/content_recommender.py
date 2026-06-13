from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neighbors import NearestNeighbors

from .analytics import clamp


@dataclass(frozen=True)
class ContentScoreResult:
    scores: dict[str, float]
    metadata: dict[str, Any]


def score_content_similarity(profile: dict[str, Any], catalog: list[dict[str, Any]]) -> ContentScoreResult:
    """Stage 2 recommender: match problem vectors to the user's weakness vector.

    Problems are represented as one-hot tag features plus normalized difficulty,
    popularity, and recency. The user vector represents what they need next:
    weak tags get larger weights and the target difficulty is slightly above the
    inferred current rating.
    """

    problem_rows = [_problem_vector(problem) for problem in catalog]
    user_row = _user_need_vector(profile)
    keys = [problem["key"] for problem in catalog]

    vectorizer = DictVectorizer(sparse=True)
    x_problem = vectorizer.fit_transform(problem_rows)
    x_user = vectorizer.transform([user_row])

    cosine_scores = np.asarray(cosine_similarity(x_problem, x_user)).ravel()
    if cosine_scores.size and cosine_scores.max() > cosine_scores.min():
        cosine_scores = (cosine_scores - cosine_scores.min()) / (cosine_scores.max() - cosine_scores.min())

    knn_neighbors = min(50, max(1, len(catalog)))
    knn = NearestNeighbors(n_neighbors=knn_neighbors, metric="cosine")
    knn.fit(x_problem)
    distances, indices = knn.kneighbors(x_user)
    knn_scores = {keys[index]: clamp(1 - float(distance)) for distance, index in zip(distances[0], indices[0])}

    blended_scores = {}
    for key, cosine_score in zip(keys, cosine_scores):
        blended_scores[key] = round(clamp(0.82 * float(cosine_score) + 0.18 * knn_scores.get(key, 0.0)), 4)

    return ContentScoreResult(
        scores=blended_scores,
        metadata={
            "name": "Stage 2 Content-Based Recommender",
            "status": "active",
            "method": "Cosine similarity + KNN over problem vectors",
            "problem_vector": ["rating_scaled", "rating_gap_target", "tag one-hot", "popularity", "recency"],
            "user_vector": ["target_rating", "tag weakness weights", "preferred growth band"],
            "candidate_count": len(catalog),
            "feature_count": len(vectorizer.vocabulary_),
            "focus_tags": profile["summary"]["weak_tags"][:5],
        },
    )


def _problem_vector(problem: dict[str, Any]) -> dict[str, float]:
    rating = int(problem["rating"])
    vector: dict[str, float] = {
        "rating_scaled": rating / 4000,
        f"rating_bucket={(rating // 100) * 100}": 1.0,
        "popularity": math.log1p(problem["solved_count"]) / 12,
        "recency": clamp((problem["contest_id"] - 900) / 1400),
    }
    for tag in problem["tags"]:
        vector[f"tag={tag}"] = 1.0
    return vector


def _user_need_vector(profile: dict[str, Any]) -> dict[str, float]:
    summary = profile["summary"]
    target_rating = int(summary["inferred_rating"]) + 150
    topic_by_tag = {row["tag"]: row for row in profile["topic_stats"]}

    vector: dict[str, float] = {
        "rating_scaled": target_rating / 4000,
        f"rating_bucket={(target_rating // 100) * 100}": 1.0,
        "popularity": 0.72,
        "recency": 0.62,
    }

    weak_tags = summary["weak_tags"][:6]
    if weak_tags:
        for tag in weak_tags:
            stat = topic_by_tag.get(tag, {})
            vector[f"tag={tag}"] = clamp(0.35 + float(stat.get("weakness_score", 0.5)))
    else:
        for tag in summary["strong_tags"][:3]:
            vector[f"tag={tag}"] = 0.45

    return vector

