from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from search_service.models import SearchRequest, normalize_result
from search_service.provider import DuckDuckGoProvider, SearchProvider, SearchProviderError


@dataclass(frozen=True)
class Settings:
    service_token: str
    version: str = "0.1.0"


def _token_valid(settings: Settings, value: str | None) -> bool:
    return value is not None and hmac.compare_digest(value, settings.service_token)


def create_app(settings: Settings | None = None, provider: SearchProvider | None = None) -> FastAPI:
    app = FastAPI(title="ai-scrivener-search", version="0.1.0")
    app.state.settings = settings or Settings(service_token="")
    app.state.provider = provider or DuckDuckGoProvider()

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        current: Settings = request.app.state.settings
        return {"status": "ok", "version": current.version, "provider": "duckduckgo"}

    @app.post("/v1/search")
    async def search(
        request: Request,
        payload: SearchRequest,
        x_service_token: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        current: Settings = request.app.state.settings
        if not _token_valid(current, x_service_token):
            return JSONResponse(status_code=401, content={"detail": "invalid service token"})
        started = time.monotonic()
        try:
            raw = await request.app.state.provider.search(
                payload.query,
                payload.limit,
                payload.locale,
                payload.safe_search,
            )
        except SearchProviderError as exc:
            return JSONResponse(status_code=502, content={"detail": str(exc)})
        results = [normalize_result(item, index) for index, item in enumerate(raw)]
        return JSONResponse(
            content={
                "results": results,
                "provider": "duckduckgo",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )

    return app
