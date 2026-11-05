from __future__ import annotations

import pytest

from tools.llm_eval.clients import extract_json
from tools.llm_eval.metrics import CaseResult, aggregate, find_rank
from tools.llm_eval.run import (
    Candidate,
    build_context,
    flatten_candidates,
    normalize_citations,
)


def test_extract_json_accepts_markdown_fence() -> None:
    raw = '```json\n{"found": true, "answer": "ok"}\n```'
    assert extract_json(raw) == {"found": True, "answer": "ok"}


def test_normalize_citations_accepts_labels_and_source_ids() -> None:
    candidates = [
        Candidate(
            id="K1",
            source_id="sha1",
            title="ГОСТ",
            doc_type="ГОСТ",
            section="1 Общие положения",
            clause="1.1",
            text="Текст пункта.",
            page=2,
        )
    ]
    _, allowed, sources, label_clauses = build_context(candidates)
    valid, invalid = normalize_citations(
        [
            "S1",
            {"source_id": "sha1", "clause": "1.1"},
            {"source_id": "S1", "clause": ""},
            {"source_id": "unknown", "clause": ""},
        ],
        allowed,
        sources,
        label_clauses,
    )

    assert valid == [{"source_id": "sha1", "clause": "1.1"}]
    assert invalid == 1


def test_build_context_contains_label_and_metadata() -> None:
    candidates = [
        Candidate(
            id="K1",
            source_id="sha1",
            title="ГОСТ 1",
            doc_type="ГОСТ",
            section="Раздел → Пункт",
            clause="4.2",
            text="Текст.",
            page=7,
        )
    ]
    context, allowed, sources, label_clauses = build_context(candidates)

    assert "[S1] Документ: ГОСТ 1" in context
    assert "вид: ГОСТ" in context
    assert "раздел: Раздел → Пункт" in context
    assert "пункт: 4.2" in context
    assert "sha1|4.2" in allowed
    assert sources["S1"] == "sha1"
    assert label_clauses["S1"] == "4.2"


def test_flatten_candidates_keeps_chunk_and_document_fields() -> None:
    results = [
        {
            "source_id": "sha1",
            "title": "ГОСТ 1",
            "metadata": {"doc_type": "ГОСТ"},
            "chunks": [
                {
                    "text": "Текст.",
                    "clause": "1.1",
                    "section_path": ["Раздел 1", "Пункт 1.1"],
                    "page_start": 3,
                }
            ],
        }
    ]

    candidates = flatten_candidates(results)

    assert len(candidates) == 1
    assert candidates[0].id == "K1"
    assert candidates[0].doc_type == "ГОСТ"
    assert candidates[0].section == "Раздел 1 → Пункт 1.1"
    assert candidates[0].clause == "1.1"
    assert candidates[0].page == 3


def test_find_rank_supports_source_and_clause_matching() -> None:
    by_source = [{"source_id": "sha1", "chunks": []}]
    assert find_rank(by_source, {"sha1"}, set()) == 1

    by_clause = [{"source_id": "other", "chunks": [{"clause": "4.2"}]}]
    assert find_rank(by_clause, {"sha1"}, {"4.2"}) == 1


def test_aggregate_counts_correctly() -> None:
    cases = [
        CaseResult(
            query="q1",
            doc_type="ГОСТ",
            no_answer=False,
            expected_sources=["sha1"],
            expected_clauses=["1.1"],
            expected_pairs=[("sha1", "1.1")],
            retrieval_rank=1,
            found=True,
            citations=[{"source_id": "sha1", "clause": "1.1"}],
            raw_citation_count=1,
            correctness=1.0,
            groundedness=1.0,
            retrieval_ms=10.0,
            e2e_ms=100.0,
        ),
        CaseResult(
            query="q2",
            doc_type="ГОСТ",
            no_answer=False,
            expected_sources=["sha2"],
            expected_clauses=["2.1"],
            expected_pairs=[("sha2", "2.1")],
            retrieval_rank=2,
            found=True,
            citations=[{"source_id": "sha2", "clause": "2.1"}],
            raw_citation_count=2,
            invalid_citation_count=1,
            correctness=0.5,
            groundedness=0.5,
            retrieval_ms=20.0,
            e2e_ms=200.0,
        ),
        CaseResult(
            query="q3",
            doc_type="ГОСТ",
            no_answer=False,
            expected_sources=["sha3"],
            expected_clauses=["3.1"],
            expected_pairs=[("sha3", "3.1")],
            found=False,
            correctness=0.0,
            retrieval_ms=30.0,
            e2e_ms=300.0,
        ),
        CaseResult(
            query="q4",
            doc_type="",
            no_answer=True,
            found=False,
            retrieval_ms=40.0,
            e2e_ms=400.0,
        ),
        CaseResult(
            query="q5",
            doc_type="",
            no_answer=True,
            found=True,
            retrieval_ms=50.0,
            e2e_ms=500.0,
        ),
    ]

    metrics = aggregate(cases, top_k=10)
    retrieval = metrics["retrieval"]
    answer = metrics["answer"]

    assert retrieval["answerable_cases"] == 3
    assert retrieval["recall_at_k"] == pytest.approx(0.6667)
    assert retrieval["mrr_at_k"] == pytest.approx(0.5)
    assert retrieval["no_answer_accuracy"] == 0.0
    assert answer["citation_precision"] == pytest.approx(0.6667)
    assert answer["citation_recall"] == pytest.approx(0.6667)
    assert answer["citation_accuracy"] == pytest.approx(0.5)
    assert answer["correctness"] == pytest.approx(0.5)
    assert answer["groundedness"] == pytest.approx(0.75)
    assert answer["no_answer_precision"] == pytest.approx(0.5)
    assert answer["no_answer_recall"] == pytest.approx(0.5)
    assert answer["false_refusals"] == 1
    assert answer["hallucinated_answers"] == 1
    assert answer["errors"] == 0
