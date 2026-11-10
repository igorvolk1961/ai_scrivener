from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from search_service.config import Settings, load_settings
from search_service.models import SearchRequest, normalize_result
from search_service.provider import DuckDuckGoProvider, SearchProvider, SearchProviderError


def create_app(settings: Settings | None = None, provider: SearchProvider | None = None) -> FastAPI:
    app = FastAPI(title="ai-scrivener-search", version="0.1.0")
    app.state.settings = settings or load_settings()
    app.state.provider = provider or DuckDuckGoProvider(
        timeout_seconds=app.state.settings.timeout_seconds
    )

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        current: Settings = request.app.state.settings
        return {
            "status": "ok",
            "version": current.version,
            "provider": current.provider,
        }

    @app.post("/v1/search")
    async def search(
        request: Request,
        payload: SearchRequest,
    ) -> JSONResponse:
        current: Settings = request.app.state.settings
        started = time.monotonic()
        limit = min(payload.limit, current.max_results)
        try:
            raw = await request.app.state.provider.search(
                payload.query,
                limit,
                payload.locale,
                payload.safe_search,
            )
        except SearchProviderError as exc:
            return JSONResponse(status_code=502, content={"detail": str(exc)})
        results = [normalize_result(item, index) for index, item in enumerate(raw[:limit])]
        return JSONResponse(
            content={
                "results": results,
                "provider": current.provider,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )

    return app
