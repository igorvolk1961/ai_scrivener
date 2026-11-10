from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_token: str
    llm_api_key: str
    llm_base_url: str
    request_timeout_seconds: float
    version: str = "0.1.0"


def load_settings() -> Settings:
    token = os.environ.get("AGENT_SERVICE_TOKEN", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not token:
        raise RuntimeError("AGENT_SERVICE_TOKEN is not set")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set")
    return Settings(
        service_token=token,
        llm_api_key=api_key,
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        request_timeout_seconds=float(os.environ.get("AGENT_REQUEST_TIMEOUT", "60")),
    )
