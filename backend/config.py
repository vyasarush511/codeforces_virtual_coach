from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "Codeforces Virtual Coach"
    codeforces_base_url: str = "https://codeforces.com/api"
    cache_path: Path = PROJECT_DIR / "data" / "cf_cache.sqlite3"
    user_cache_ttl_seconds: int = 15 * 60
    problemset_cache_ttl_seconds: int = 12 * 60 * 60
    system_cache_ttl_seconds: int = 60
    request_timeout_seconds: float = 45.0
    max_submissions: int = 10000
    default_recommendations: int = 24
    user_agent: str = "cf-virtual-coach/1.0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        codeforces_base_url=os.getenv("CODEFORCES_BASE_URL", Settings.codeforces_base_url),
        cache_path=Path(os.getenv("CF_COACH_CACHE_PATH", str(Settings.cache_path))),
        user_cache_ttl_seconds=int(os.getenv("USER_CACHE_TTL_SECONDS", Settings.user_cache_ttl_seconds)),
        problemset_cache_ttl_seconds=int(
            os.getenv("PROBLEMSET_CACHE_TTL_SECONDS", Settings.problemset_cache_ttl_seconds)
        ),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", Settings.request_timeout_seconds)),
        max_submissions=int(os.getenv("MAX_SUBMISSIONS", Settings.max_submissions)),
    )
