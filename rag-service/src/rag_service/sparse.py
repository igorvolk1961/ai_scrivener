from __future__ import annotations

import asyncio
from typing import Protocol

from qdrant_client import models


class SparseEncoderError(RuntimeError):
    pass


class SparseEncoder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[models.SparseVector]: ...

    async def embed_query(self, text: str) -> models.SparseVector: ...

    async def close(self) -> None: ...


class FastEmbedSparseEncoder:
    def __init__(self, model_name: str, language: str, avg_len: float) -> None:
        try:
            from fastembed.sparse.bm25 import Bm25
        except ImportError as error:
            raise SparseEncoderError("fastembed is not installed") from error
        self._model = Bm25(model_name=model_name, language=language, avg_len=avg_len)

    async def embed_documents(self, texts: list[str]) -> list[models.SparseVector]:
        return await asyncio.to_thread(self._embed_documents, texts)

    async def embed_query(self, text: str) -> models.SparseVector:
        return await asyncio.to_thread(self._embed_query, text)

    async def close(self) -> None:
        return None

    def _embed_documents(self, texts: list[str]) -> list[models.SparseVector]:
        return [self._to_vector(embedding) for embedding in self._model.embed(texts)]

    def _embed_query(self, text: str) -> models.SparseVector:
        return self._to_vector(next(iter(self._model.query_embed(text))))

    @staticmethod
    def _to_vector(embedding: object) -> models.SparseVector:
        indices = getattr(embedding, "indices", None)
        values = getattr(embedding, "values", None)
        if indices is None or values is None:
            raise SparseEncoderError("invalid sparse embedding")
        return models.SparseVector(
            indices=[int(index) for index in indices],
            values=[float(value) for value in values],
        )
