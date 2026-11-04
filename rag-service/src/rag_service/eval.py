from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_source_ids: tuple[str, ...] = ()
    expected_clauses: tuple[str, ...] = ()
    filters: dict[str, Any] = field(default_factory=dict)
    no_answer: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvalCase:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("eval case is missing query")
        return cls(
            query=query,
            expected_source_ids=tuple(
                str(item) for item in payload.get("expected_source_ids", [])
            ),
            expected_clauses=tuple(
                str(item) for item in payload.get("expected_clauses", [])
            ),
            filters=dict(payload.get("filters", {})),
            no_answer=bool(payload.get("no_answer", False)),
        )


@dataclass
class CaseResult:
    query: str
    rank: int | None
    recall: float
    mrr: float
    ndcg: float
    no_answer_ok: bool | None
    answerable: bool
    latency_ms: float
    results: list[dict[str, Any]]


@dataclass
class EvalReport:
    cases: list[CaseResult]
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "cases": [
                {
                    "query": case.query,
                    "rank": case.rank,
                    "recall": case.recall,
                    "mrr": case.mrr,
                    "ndcg": case.ndcg,
                    "no_answer_ok": case.no_answer_ok,
                    "answerable": case.answerable,
                    "latency_ms": case.latency_ms,
                    "results": case.results,
                }
                for case in self.cases
            ],
        }


class EvalClient(Protocol):
    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> dict[str, Any]: ...


class HttpEvalClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"X-Service-Token": token},
        )
        self._owns_client = client is None

    async def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/retrieve",
            json={"query": query, "filters": filters, "top_k": top_k},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid /v1/retrieve response")
        return payload

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("eval case must be a JSON object")
                cases.append(EvalCase.from_dict(payload))
            except (json.JSONDecodeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return cases


async def run_eval(
    client: EvalClient,
    cases: list[EvalCase],
    top_k: int = 10,
) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        started = time.perf_counter()
        payload = await client.retrieve(case.query, case.filters, top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        ranked = list(payload.get("results", []))[:top_k]
        rank = _find_rank(case, ranked)
        recall = 1.0 if rank is not None else 0.0
        mrr = 1.0 / rank if rank is not None else 0.0
        ndcg = _ndcg(case, rank, top_k)
        no_answer_ok = None if not case.no_answer else not ranked
        results.append(
            CaseResult(
                query=case.query,
                rank=rank,
                recall=recall,
                mrr=mrr,
                ndcg=ndcg,
                no_answer_ok=no_answer_ok,
                answerable=bool(case.expected_source_ids or case.expected_clauses),
                latency_ms=round(latency_ms, 2),
                results=ranked,
            )
        )
    return EvalReport(cases=results, metrics=_metrics(results))


def _find_rank(case: EvalCase, ranked: list[dict[str, Any]]) -> int | None:
    if not case.expected_source_ids and not case.expected_clauses:
        return None
    for position, result in enumerate(ranked, start=1):
        source_id = str(result.get("source_id", ""))
        if case.expected_source_ids and source_id in case.expected_source_ids:
            return position
        if case.expected_clauses:
            clauses = {
                str(chunk.get("clause", ""))
                for chunk in result.get("chunks", [])
                if isinstance(chunk, dict)
            }
            if clauses & set(case.expected_clauses):
                return position
    return None


def _ndcg(case: EvalCase, rank: int | None, top_k: int) -> float:
    if rank is None:
        return 0.0
    relevant = len(case.expected_source_ids) or len(case.expected_clauses) or 1
    ideal = 0.0
    position = 1
    limit = min(relevant, top_k)
    while position <= limit:
        ideal += 1.0 / _log2(position + 1)
        position += 1
    if ideal == 0:
        return 0.0
    return (1.0 / _log2(rank + 1)) / ideal


def _metrics(cases: list[CaseResult]) -> dict[str, float]:
    answerable = [case for case in cases if case.answerable]
    no_answer = [case for case in cases if case.no_answer_ok is not None]
    metrics: dict[str, float] = {
        "cases": float(len(cases)),
        "answerable_cases": float(len(answerable)),
        "recall_at_k": _mean([case.recall for case in answerable]),
        "mrr_at_k": _mean([case.mrr for case in answerable]),
        "ndcg_at_k": _mean([case.ndcg for case in answerable]),
        "no_answer_accuracy": _mean(
            [1.0 if case.no_answer_ok else 0.0 for case in no_answer]
        ),
        "latency_p50_ms": _percentile([case.latency_ms for case in cases], 50),
        "latency_p95_ms": _percentile([case.latency_ms for case in cases], 95),
    }
    return {key: round(value, 4) for key, value in metrics.items()}


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round(percentile / 100 * (len(ordered) - 1))
    return ordered[max(0, min(len(ordered) - 1, index))]


def _log2(value: int) -> float:
    return 1.0 if value <= 1 else math.log2(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag_eval")
    parser.add_argument("--base-url", default=os.environ.get("RAG_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--token", default=os.environ.get("RAG_SERVICE_TOKEN", ""))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    return parser


async def _run(args: argparse.Namespace) -> int:
    cases = load_cases(args.dataset)
    if not cases:
        print("no eval cases", file=sys.stderr)
        return 1
    client = HttpEvalClient(args.base_url, args.token)
    try:
        report = await run_eval(client, cases, args.top_k)
    finally:
        await client.close()
    payload = report.to_dict()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report.metrics, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, ValueError, httpx.HTTPError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
