from __future__ import annotations

import asyncio
from typing import Protocol


class RerankerError(RuntimeError):
    pass


class Reranker(Protocol):
    async def score(self, query: str, documents: list[str]) -> list[float]: ...

    async def close(self) -> None: ...


class FastEmbedReranker:
    def __init__(self, model_name: str, batch_size: int) -> None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError as error:
            raise RerankerError("fastembed is not installed") from error
        self._model = TextCrossEncoder(model_name=model_name)
        self._batch_size = batch_size

    async def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        return await asyncio.to_thread(
            self._score, query, documents
        )

    async def close(self) -> None:
        return None

    def _score(self, query: str, documents: list[str]) -> list[float]:
        return [
            float(score)
            for score in self._model.rerank(
                query,
                documents,
                batch_size=self._batch_size,
            )
        ]
