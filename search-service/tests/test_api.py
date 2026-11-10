from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from search_service.config import Settings, load_settings
from search_service.main import create_app
from search_service.provider import SearchProviderError

TOKEN = "test-token"


class FakeProvider:
    def __init__(self, results: list[dict[str, Any]] | None = None, error: bool = False) -> None:
        self.results = results or []
        self.error = error
        self.last_limit: int | None = None

    async def search(
        self, query: str, limit: int, locale: str, safe_search: bool
    ) -> list[dict[str, Any]]:
        if self.error:
            raise SearchProviderError("boom")
        self.last_limit = limit
        return self.results[:limit]


def client_with(provider: FakeProvider) -> TestClient:
    app = create_app(settings=Settings(service_token=TOKEN), provider=provider)
    return TestClient(app)


def test_search_returns_normalized_results() -> None:
    client = client_with(
        FakeProvider([{"title": "Заголовок", "url": "https://example.com", "snippet": "Фрагмент"}])
    )
    response = client.post(
        "/v1/search",
        json={"query": "тест", "limit": 5},
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["rank"] == 0
    assert body["results"][0]["source"] == "internet"


def test_search_requires_token() -> None:
    client = client_with(FakeProvider())
    response = client.post("/v1/search", json={"query": "тест"})
    assert response.status_code == 401


def test_provider_error() -> None:
    client = client_with(FakeProvider(error=True))
    response = client.post(
        "/v1/search",
        json={"query": "тест"},
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 502


def test_limit_capped_by_settings() -> None:
    provider = FakeProvider(
        [
            {"title": f"Результат {index}", "url": f"https://example.com/{index}"}
            for index in range(5)
        ]
    )
    app = create_app(
        settings=Settings(service_token=TOKEN, max_results=2),
        provider=provider,
    )
    client = TestClient(app)
    response = client.post(
        "/v1/search",
        json={"query": "тест", "limit": 5},
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    assert len(response.json()["results"]) == 2
    assert provider.last_limit == 2


def test_load_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("SEARCH_TIMEOUT", "5")
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "7")
    monkeypatch.setenv("SEARCH_PROVIDER", "duckduckgo")
    settings = load_settings()
    assert settings == Settings(
        service_token=TOKEN,
        timeout_seconds=5.0,
        max_results=7,
        provider="duckduckgo",
    )


def test_load_settings_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARCH_SERVICE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="SEARCH_SERVICE_TOKEN"):
        load_settings()


def test_load_settings_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("SEARCH_PROVIDER", "unknown")
    with pytest.raises(RuntimeError, match="SEARCH_PROVIDER"):
        load_settings()
