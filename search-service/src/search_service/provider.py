from __future__ import annotations

import re
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

import httpx


class SearchProvider(Protocol):
    async def search(
        self, query: str, limit: int, locale: str, safe_search: bool
    ) -> list[dict[str, Any]]: ...


class SearchProviderError(RuntimeError):
    pass


def _clean(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).replace("&amp;", "&").strip()


def _target_url(href: str) -> str:
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return values[0]
    return href


class DuckDuckGoProvider:
    def __init__(
        self,
        timeout_seconds: float = 20.0,
        user_agent: str = "ai-scrivener-search/0.1",
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def search(
        self, query: str, limit: int, locale: str, safe_search: bool
    ) -> list[dict[str, Any]]:
        params = {"q": query, "kl": f"{locale}-{locale}"}
        if safe_search:
            params["kp"] = "1"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params=params,
                    headers={"User-Agent": self._user_agent},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchProviderError(f"search provider failed: {exc}") from exc

        results: list[dict[str, Any]] = []
        pattern = re.compile(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippets = re.findall(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            response.text,
            re.IGNORECASE | re.DOTALL,
        )
        for index, match in enumerate(pattern.finditer(response.text)):
            if len(results) >= limit:
                break
            url = _target_url(match.group(1))
            title = _clean(match.group(2))
            snippet = _clean(snippets[index]) if index < len(snippets) else ""
            if not url or not title:
                continue
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": "internet",
                }
            )
        return results
