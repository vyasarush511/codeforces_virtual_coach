from __future__ import annotations

import json
import asyncio
from typing import Any

import httpx

from .cache import SQLiteCache
from .config import Settings, get_settings


class CodeforcesAPIError(RuntimeError):
    pass


class CodeforcesClient:
    def __init__(self, settings: Settings | None = None, cache: SQLiteCache | None = None):
        self.settings = settings or get_settings()
        self.cache = cache or SQLiteCache(self.settings.cache_path)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "CodeforcesClient":
        self._client = httpx.AsyncClient(
            base_url=self.settings.codeforces_base_url,
            timeout=httpx.Timeout(self.settings.request_timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            follow_redirects=True,
            headers={"User-Agent": self.settings.user_agent},
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client:
            await self._client.aclose()

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        ttl_seconds: int = 300,
        force_refresh: bool = False,
    ) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cache_key = self._cache_key(method, params)
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        if self._client is None:
            raise CodeforcesAPIError("Client must be used as an async context manager")

        response = await self._request_with_retries(method, params)
        payload = response.json()
        if payload.get("status") != "OK":
            comment = payload.get("comment", "Unknown Codeforces API error")
            raise CodeforcesAPIError(comment)

        result = payload.get("result")
        self.cache.set(cache_key, result, ttl_seconds)
        return result

    async def user_info(self, handle: str, force_refresh: bool = False) -> list[dict[str, Any]]:
        return await self.call(
            "user.info",
            {"handles": handle, "checkHistoricHandles": "false"},
            ttl_seconds=self.settings.user_cache_ttl_seconds,
            force_refresh=force_refresh,
        )

    async def user_status(self, handle: str, count: int, force_refresh: bool = False) -> list[dict[str, Any]]:
        return await self.call(
            "user.status",
            {"handle": handle, "from": 1, "count": count},
            ttl_seconds=self.settings.user_cache_ttl_seconds,
            force_refresh=force_refresh,
        )

    async def user_rating(self, handle: str, force_refresh: bool = False) -> list[dict[str, Any]]:
        return await self.call(
            "user.rating",
            {"handle": handle},
            ttl_seconds=self.settings.user_cache_ttl_seconds,
            force_refresh=force_refresh,
        )

    async def problemset(self, force_refresh: bool = False) -> dict[str, Any]:
        return await self.call(
            "problemset.problems",
            ttl_seconds=self.settings.problemset_cache_ttl_seconds,
            force_refresh=force_refresh,
        )

    async def system_status(self) -> dict[str, Any] | None:
        try:
            return await self.call(
                "system.status",
                ttl_seconds=self.settings.system_cache_ttl_seconds,
            )
        except Exception:
            return None

    @staticmethod
    def _cache_key(method: str, params: dict[str, Any]) -> str:
        return f"{method}:{json.dumps(params, sort_keys=True, separators=(',', ':'))}"

    async def _request_with_retries(self, method: str, params: dict[str, Any]) -> httpx.Response:
        if self._client is None:
            raise CodeforcesAPIError("Client must be used as an async context manager")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self._client.get(f"/{method}", params=params)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                await asyncio.sleep(0.7 * (attempt + 1))
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    last_error = exc
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise

        raise CodeforcesAPIError(f"Codeforces request failed for {method}: {last_error}")
