from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from rag_indexer.client import RagClient

LIVE_URL = os.environ.get("RAG_LIVE_URL", "")
LIVE_TOKEN = os.environ.get("RAG_LIVE_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not LIVE_URL or not LIVE_TOKEN,
    reason="RAG_LIVE_URL and RAG_LIVE_TOKEN are required for live integration tests",
)


def test_live_index_retrieve_delete() -> None:
    source_id = f"integration-{uuid.uuid4()}"

    async def run() -> None:
        client = RagClient(LIVE_URL, LIVE_TOKEN)
        try:
            health = await client.health()
            assert health["status"] == "ok"

            await client.index_chunks(
                {
                    "source_type": "integration_test",
                    "document": {
                        "source_id": source_id,
                        "version": "1",
                        "title": "Интеграционный тест",
                        "metadata": {
                            "doc_type": "test",
                            "status": "verified",
                        },
                    },
                    "replace_existing": True,
                    "active": True,
                    "chunks": [
                        {
                            "index": 0,
                            "text": "Интеграционный тест проверяет поиск и удаление.",
                            "embedding_text": (
                                "Документ: Интеграционный тест\n"
                                "Текст: Интеграционный тест проверяет поиск и удаление."
                            ),
                            "kind": "paragraph",
                            "metadata": {},
                        }
                    ],
                }
            )
            result = await client.retrieve(
                "интеграционный тест",
                {"source_types": ["integration_test"], "active": True},
                5,
            )
            assert any(
                item["source_id"] == source_id for item in result["results"]
            )
        finally:
            try:
                await client.delete("integration_test", source_id)
            finally:
                await client.close()

    asyncio.run(run())
