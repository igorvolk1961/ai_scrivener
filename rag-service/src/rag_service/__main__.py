from __future__ import annotations

import uvicorn

from rag_service.config import load_parameters


def main() -> None:
    parameters = load_parameters()
    uvicorn.run(
        "rag_service.main:app",
        host="0.0.0.0",
        port=parameters.service.port,
        workers=parameters.service.workers,
        timeout_graceful_shutdown=parameters.service.graceful_shutdown_seconds,
    )


if __name__ == "__main__":
    main()
