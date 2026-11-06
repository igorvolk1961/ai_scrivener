from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaseResult:
    query: str
    doc_type: str
    no_answer: bool
    expected_sources: list[str] = field(default_factory=list)
    expected_clauses: list[str] = field(default_factory=list)
    expected_pairs: list[tuple[str, str]] = field(default_factory=list)
    retrieval_rank: int | None = None
    retrieval_empty: bool = False
    retrieval_ms: float = 0.0
    found: bool = False
    answer: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)
    raw_citation_count: int = 0
    invalid_citation_count: int = 0
    expected_clause_in_context: bool = False
    rerank_fallback: bool = False
    rerank_empty: bool = False
    rag_rerank_used: bool = False
    listwise_used: bool = False
    rerank_error: str | None = None
    raw_citations: list[dict[str, str]] = field(default_factory=list)
    correctness: float | None = None
    groundedness: float | None = None
    e2e_ms: float = 0.0
    judge_error: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "doc_type": self.doc_type,
            "no_answer": self.no_answer,
            "expected_sources": self.expected_sources,
            "expected_clauses": self.expected_clauses,
            "retrieval_rank": self.retrieval_rank,
            "retrieval_empty": self.retrieval_empty,
            "retrieval_ms": round(self.retrieval_ms, 2),
            "found": self.found,
            "answer": self.answer,
            "citations": self.citations,
            "raw_citation_count": self.raw_citation_count,
            "invalid_citation_count": self.invalid_citation_count,
            "expected_clause_in_context": self.expected_clause_in_context,
            "rerank_fallback": self.rerank_fallback,
            "rerank_empty": self.rerank_empty,
            "rag_rerank_used": self.rag_rerank_used,
            "listwise_used": self.listwise_used,
            "rerank_error": self.rerank_error,
            "raw_citations": self.raw_citations,
            "correctness": self.correctness,
            "groundedness": self.groundedness,
            "e2e_ms": round(self.e2e_ms, 2),
            "judge_error": self.judge_error,
            "error": self.error,
        }


def find_rank(
    results: list[Any],
    expected_sources: set[str],
    expected_clauses: set[str],
) -> int | None:
    """Return the 1-based rank of the first document or chunk-level clause match."""

    for position, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        source_id = str(result.get("source_id", ""))
        if expected_sources and source_id in expected_sources:
            return position
        if expected_clauses:
            chunks = result.get("chunks")
            if not isinstance(chunks, list):
                continue
            clauses = {str(chunk.get("clause", "")) for chunk in chunks if isinstance(chunk, dict)}
            if clauses & expected_clauses:
                return position
    return None


def ndcg(rank: int | None, expected_count: int, top_k: int) -> float:
    if rank is None:
        return 0.0
    relevant = max(1, expected_count)
    ideal = 0.0
    position = 1
    limit = min(relevant, top_k)
    while position <= limit:
        ideal += 1.0 / _log2(position + 1)
        position += 1
    if ideal == 0:
        return 0.0
    return (1.0 / _log2(rank + 1)) / ideal


def percentile(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round(value / 100 * (len(ordered) - 1))
    return ordered[max(0, min(len(ordered) - 1, index))]


def _log2(value: int) -> float:
    return 1.0 if value <= 1 else math.log2(value)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def aggregate(cases: list[CaseResult], top_k: int) -> dict[str, Any]:
    answerable_all = [case for case in cases if not case.no_answer]
    no_answer_all = [case for case in cases if case.no_answer]
    scored = [case for case in cases if case.error is None]
    answerable = [case for case in scored if not case.no_answer]
    no_answer = [case for case in scored if case.no_answer]

    ranks = [case.retrieval_rank for case in answerable_all]
    recalls = [1.0 if rank is not None else 0.0 for rank in ranks]
    reciprocal_ranks = [1.0 / rank if rank else 0.0 for rank in ranks]
    ndcgs = [
        ndcg(
            case.retrieval_rank,
            len(case.expected_sources) or len(case.expected_clauses) or 1,
            top_k,
        )
        for case in answerable_all
    ]

    predicted_found = [case for case in answerable if case.found]
    judged_correctness = [case.correctness for case in answerable if case.correctness is not None]
    groundedness = [case.groundedness for case in predicted_found if case.groundedness is not None]

    total_raw_citations = sum(case.raw_citation_count for case in scored)
    total_valid_citations = sum(len(case.citations) for case in scored)
    citation_precision = (
        total_valid_citations / total_raw_citations if total_raw_citations else None
    )

    citation_recalls = [_citation_recall(case) for case in answerable if case.expected_pairs]
    citation_accuracy_cases = [
        1.0 if _strict_citation_ok(case) else 0.0 for case in predicted_found if not case.no_answer
    ]

    true_positive = sum(1 for case in no_answer if not case.found)
    false_positive = sum(1 for case in answerable if not case.found)
    false_negative = sum(1 for case in no_answer if case.found)

    retrieval = {
        "cases": len(cases),
        "answerable_cases": len(answerable_all),
        "no_answer_cases": len(no_answer_all),
        "scored_cases": len(scored),
        "recall_at_k": _round(_mean(recalls)),
        "mrr_at_k": _round(_mean(reciprocal_ranks)),
        "ndcg_at_k": _round(_mean(ndcgs)),
        "no_answer_accuracy": _round(
            _mean([1.0 if case.retrieval_empty else 0.0 for case in no_answer_all])
        ),
        "latency_p50_ms": _round(percentile([case.retrieval_ms for case in cases], 50)),
        "latency_p95_ms": _round(percentile([case.retrieval_ms for case in cases], 95)),
    }

    answer = {
        "found_rate": _round(_mean([1.0 if case.found else 0.0 for case in answerable])),
        "false_refusal_rate": _round(
            _mean([1.0 if not case.found else 0.0 for case in answerable])
        ),
        "expected_clause_in_context_rate": _round(
            _mean([1.0 if case.expected_clause_in_context else 0.0 for case in answerable])
        ),
        "false_refusals_with_context": sum(
            1 for case in answerable if not case.found and case.expected_clause_in_context
        ),
        "answers_without_citations": sum(1 for case in predicted_found if not case.citations),
        "citation_precision": _round(citation_precision),
        "citation_recall": _round(_mean(citation_recalls)),
        "citation_accuracy": _round(_mean(citation_accuracy_cases)),
        "correctness": _round(_mean(judged_correctness)),
        "correctness_cases": len(judged_correctness),
        "groundedness": _round(_mean(groundedness)),
        "groundedness_cases": len(groundedness),
        "no_answer_precision": _round(
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else None
        ),
        "no_answer_recall": _round(
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else None
        ),
        "true_no_answer": true_positive,
        "false_refusals": false_positive,
        "hallucinated_answers": false_negative,
        "rerank_fallbacks": sum(1 for case in cases if case.rerank_fallback),
        "rerank_empty_rankings": sum(1 for case in cases if case.rerank_empty),
        "rag_rerank_cases": sum(1 for case in cases if case.rag_rerank_used),
        "listwise_fallback_cases": sum(1 for case in cases if case.listwise_used),
        "judge_errors": sum(1 for case in cases if case.judge_error),
        "errors": sum(1 for case in cases if case.error),
        "e2e_latency_p50_ms": _round(percentile([case.e2e_ms for case in cases], 50)),
        "e2e_latency_p95_ms": _round(percentile([case.e2e_ms for case in cases], 95)),
    }
    return {"retrieval": retrieval, "answer": answer}


def _citation_recall(case: CaseResult) -> float:
    if not case.expected_pairs:
        return 0.0
    matched = sum(
        1
        for source_id, clause in case.expected_pairs
        if any(
            citation["source_id"] == source_id
            and (not clause or citation.get("clause", "") == clause)
            for citation in case.citations
        )
    )
    return matched / len(case.expected_pairs)


def _strict_citation_ok(case: CaseResult) -> bool:
    if not case.found or not case.citations:
        return False
    if case.invalid_citation_count != 0:
        return False
    return _citation_recall(case) > 0.0
