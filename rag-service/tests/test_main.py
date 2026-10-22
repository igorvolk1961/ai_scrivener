from __future__ import annotations

from typing import Any

import uvicorn

from rag_service import __main__ as entry
from rag_service.config import ApplicationParameters


def test_main_passes_configured_service_parameters(
    monkeypatch: Any,
    parameters: ApplicationParameters,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(*args: Any, **kwargs: Any) -> None:
        captured["args"] = args
        captured.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(entry, "load_parameters", lambda: parameters)

    entry.main()

    assert captured["port"] == parameters.service.port
    assert captured["workers"] == parameters.service.workers
    assert captured["timeout_graceful_shutdown"] == parameters.service.graceful_shutdown_seconds
