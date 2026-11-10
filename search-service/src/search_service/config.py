from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESULTS = 10
DEFAULT_PROVIDER = "duckduckgo"
SUPPORTED_PROVIDERS = frozenset({DEFAULT_PROVIDER})


@dataclass(frozen=True)
class Settings:
    service_token: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_results: int = DEFAULT_MAX_RESULTS
    provider: str = DEFAULT_PROVIDER
    version: str = "0.1.0"


def _positive_float(name: str, default: str) -> float:
    try:
        value = float(os.environ.get(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _bounded_int(name: str, default: str, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not lower <= value <= upper:
        raise RuntimeError(f"{name} must be between {lower} and {upper}")
    return value


def load_settings() -> Settings:
    token = os.environ.get("SEARCH_SERVICE_TOKEN", "").strip()

    provider = os.environ.get("SEARCH_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    provider = provider or DEFAULT_PROVIDER
    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError(f"unsupported SEARCH_PROVIDER: {provider}")

    return Settings(
        service_token=token,
        timeout_seconds=_positive_float("SEARCH_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)),
        max_results=_bounded_int(
            "SEARCH_MAX_RESULTS", str(DEFAULT_MAX_RESULTS), lower=1, upper=20
        ),
        provider=provider,
    )
