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

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> dict[str, Any]:
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
