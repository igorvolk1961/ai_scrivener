from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

import pytest

from rag_service.eval import EvalCase, load_cases, run_eval


class FakeEvalClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses
        self.scopes: dict[str, str] = {}

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int,
        scope: str = "knowledge",
    ) -> dict[str, Any]:
        self.scopes[query] = scope
        return self._responses[query]


def test_load_cases(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "query": "вопрос",
                "expected_source_ids": ["a"],
                "filters": {"source_types": ["template_internal"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(path)

    assert len(cases) == 1
    assert cases[0].query == "вопрос"
    assert cases[0].expected_source_ids == ("a",)
    assert cases[0].filters["source_types"] == ["template_internal"]


def test_load_cases_rejects_invalid_case(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text('{"expected_source_ids": ["a"]}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        load_cases(path)


def test_run_eval_computes_metrics() -> None:
    cases = [
        EvalCase(query="first", expected_source_ids=("a",)),
        EvalCase(query="clause", expected_clauses=("4.2",)),
        EvalCase(query="missing", expected_source_ids=("c",)),
        EvalCase(query="no-answer", no_answer=True),
    ]
    client = FakeEvalClient(
        {
            "first": {
                "results": [
                    {"source_id": "b", "chunks": []},
                    {"source_id": "a", "chunks": []},
                ]
            },
            "clause": {
                "results": [
                    {"source_id": "x", "chunks": [{"clause": "4.2"}]},
                ]
            },
            "missing": {"results": [{"source_id": "x", "chunks": []}]},
            "no-answer": {"results": []},
        }
    )

    report = asyncio.run(run_eval(client, cases, top_k=10))

    assert report.cases[0].rank == 2
    assert report.cases[0].mrr == 0.5
    assert report.cases[1].rank == 1
    assert report.cases[1].ndcg == 1.0
    assert report.cases[2].rank is None
    assert report.cases[3].no_answer_ok is True
    assert report.metrics["answerable_cases"] == 3
    assert report.metrics["recall_at_k"] == pytest.approx(2 / 3, rel=1e-3)
    assert report.metrics["mrr_at_k"] == pytest.approx(0.5, rel=1e-3)
    assert report.metrics["ndcg_at_k"] == pytest.approx(
        (1 / math.log2(3) + 1.0) / 3,
        rel=1e-3,
    )
    assert report.metrics["no_answer_accuracy"] == 1.0
    assert report.metrics["stale_cases"] == 0.0
    assert report.metrics["acl_cases"] == 0.0
    assert report.metrics["current_version_cases"] == 0.0


def test_load_cases_reads_document_fields(tmp_path: Path) -> None:
    path = tmp_path / "documents.jsonl"
    path.write_text(
        json.dumps(
            {
                "query": "актуальный приказ",
                "scope": "documents",
                "expected_source_ids": ["current"],
                "stale_source_ids": ["old"],
                "forbidden_source_ids": ["secret"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_cases(path)

    assert cases[0].scope == "documents"
    assert cases[0].stale_source_ids == ("old",)
    assert cases[0].forbidden_source_ids == ("secret",)


def test_load_cases_rejects_unknown_scope(tmp_path: Path) -> None:
    path = tmp_path / "documents.jsonl"
    path.write_text('{"query": "q", "scope": "all"}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        load_cases(path)


def test_run_eval_document_metrics() -> None:
    cases = [
        EvalCase(
            query="clean",
            scope="documents",
            expected_source_ids=("current",),
            stale_source_ids=("old",),
            forbidden_source_ids=("secret",),
        ),
        EvalCase(
            query="stale-leak",
            scope="documents",
            expected_source_ids=("current",),
            stale_source_ids=("old",),
            forbidden_source_ids=("secret",),
        ),
        EvalCase(
            query="acl-leak",
            scope="documents",
            expected_source_ids=("current",),
            stale_source_ids=("old",),
            forbidden_source_ids=("secret",),
        ),
        EvalCase(query="no-answer", scope="documents", no_answer=True),
    ]
    client = FakeEvalClient(
        {
            "clean": {
                "results": [
                    {"source_id": "current", "chunks": [{"is_current": True}]},
                ]
            },
            "stale-leak": {
                "results": [
                    {"source_id": "current", "chunks": []},
                    {"source_id": "old", "chunks": []},
                ]
            },
            "acl-leak": {
                "results": [
                    {"source_id": "secret", "chunks": []},
                    {"source_id": "current", "chunks": []},
                ]
            },
            "no-answer": {"results": []},
        }
    )

    report = asyncio.run(run_eval(client, cases, top_k=10))

    assert client.scopes == {
        "clean": "documents",
        "stale-leak": "documents",
        "acl-leak": "documents",
        "no-answer": "documents",
    }
    assert report.metrics["document_cases"] == 4.0
    assert report.metrics["stale_cases"] == 3.0
    assert report.metrics["stale_version_leak_rate"] == pytest.approx(1 / 3, rel=1e-3)
    assert report.metrics["acl_cases"] == 3.0
    assert report.metrics["acl_leak_rate"] == pytest.approx(1 / 3, rel=1e-3)
    assert report.metrics["current_version_cases"] == 3.0
    assert report.metrics["current_version_accuracy"] == pytest.approx(2 / 3, rel=1e-3)
    assert report.cases[0].current_version_ok is True
    assert report.cases[1].stale_leak is True
    assert report.cases[2].acl_leak is True
    assert report.cases[3].no_answer_ok is True


def test_run_eval_detects_stale_from_result_metadata() -> None:
    cases = [
        EvalCase(
            query="q",
            scope="documents",
            expected_source_ids=("current",),
            stale_source_ids=("old",),
        )
    ]
    client = FakeEvalClient(
        {
            "q": {
                "results": [
                    {
                        "source_id": "current",
                        "metadata": {"is_current": True, "status": "approved"},
                        "chunks": [],
                    },
                    {
                        "source_id": "other",
                        "metadata": {"is_current": False, "status": "superseded"},
                        "chunks": [],
                    },
                ]
            }
        }
    )

    report = asyncio.run(run_eval(client, cases, top_k=10))

    assert report.cases[0].stale_leak is True
    assert report.metrics["stale_version_leak_rate"] == 1.0
