from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache import SQLiteCache
from .cf_client import CodeforcesAPIError, CodeforcesClient
from .config import BASE_DIR, get_settings
from .models import AnalysisResponse, HealthResponse
from .services import analyze_handle


STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Codeforces Virtual Coach",
    version="1.0.0",
    description="A hybrid analytics and recommendation engine for Codeforces practice planning.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse)
async def health() -> dict:
    settings = get_settings()
    cache = SQLiteCache(settings.cache_path)
    status = None
    async with CodeforcesClient(settings=settings, cache=cache) as client:
        system = await client.system_status()
        if system:
            status = system.get("status") or "available"
    stats = cache.stats()
    return {
        "status": "ok",
        "codeforces_status": status,
        "cache_entries": stats["entries"],
        "cache_path": stats["path"],
    }


@app.get("/api/analyze/{handle}", response_model=AnalysisResponse)
async def analyze(
    handle: str,
    limit: int = Query(default=10000, ge=100, le=10000),
    force_refresh: bool = Query(default=False),
) -> dict:
    try:
        return await analyze_handle(handle=handle, limit=limit, force_refresh=force_refresh)
    except CodeforcesAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    icon = Path(STATIC_DIR / "favicon.svg")
    return FileResponse(icon)

