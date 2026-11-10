from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from search_service.main import Settings, create_app
from search_service.provider import SearchProviderError

TOKEN = "test-token"


class FakeProvider:
    def __init__(self, results: list[dict[str, Any]] | None = None, error: bool = False) -> None:
        self.results = results or []
        self.error = error

    async def search(
        self, query: str, limit: int, locale: str, safe_search: bool
    ) -> list[dict[str, Any]]:
        if self.error:
            raise SearchProviderError("boom")
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
