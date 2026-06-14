from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserSummary(BaseModel):
    handle: str
    rating: int | None = None
    rank: str | None = None
    max_rating: int | None = None
    max_rank: str | None = None
    contribution: int | None = None
    friend_of_count: int | None = None
    avatar: str | None = None
    title_photo: str | None = None


class TopicStat(BaseModel):
    tag: str
    attempted: int
    solved: int
    wrong_attempts: int
    acceptance_rate: float
    avg_solved_rating: float | None = None
    max_solved_rating: int | None = None
    latest_solve_at: str | None = None
    weakness_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    level: str


class LanguageStat(BaseModel):
    language: str
    submissions: int
    accepted: int
    acceptance_rate: float


class TimelinePoint(BaseModel):
    month: str
    accepted: int
    rejected: int
    unique_solved: int


class RatingPoint(BaseModel):
    contest_id: int
    contest_name: str
    rank: int
    old_rating: int
    new_rating: int
    rating_update_time_seconds: int


class Recommendation(BaseModel):
    contest_id: int
    index: str
    name: str
    rating: int
    tags: list[str]
    solved_count: int
    url: str
    score: float
    difficulty_fit: float
    priority: str
    why: list[str]
    features: dict[str, float]


class TrainingBlock(BaseModel):
    title: str
    focus: str
    problems: list[Recommendation]


class TrainingPlan(BaseModel):
    current_band: str
    next_target_rating: int
    weekly_load: int
    focus_tags: list[str]
    blocks: list[TrainingBlock]
    milestones: list[str]


class ProfileSummary(BaseModel):
    solved_count: int
    attempted_count: int
    accepted_submissions: int
    rejected_submissions: int
    active_days: int
    best_solved_rating: int | None = None
    avg_solved_rating: float | None = None
    current_streak_days: int
    max_streak_days: int
    inferred_rating: int
    strong_tags: list[str]
    weak_tags: list[str]


class EvaluationMetrics(BaseModel):
    status: str
    k: int
    message: str | None = None
    cutoff_date: str | None = None
    train_solved: int
    holdout_solved: int
    precision_at_k: float | None = None
    hit_rate_at_k: float | None = None
    ndcg_at_k: float | None = None
    mrr: float | None = None
    hits: list[str]


class AnalysisResponse(BaseModel):
    generated_at: str
    source: str
    user: UserSummary
    profile: ProfileSummary
    topic_stats: list[TopicStat]
    languages: list[LanguageStat]
    timeline: list[TimelinePoint]
    rating_history: list[RatingPoint]
    recommender_model: dict[str, Any]
    evaluation: EvaluationMetrics
    recommendations: list[Recommendation]
    plan: TrainingPlan
    cache: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    codeforces_status: str | None = None
    cache_entries: int
    cache_path: str
