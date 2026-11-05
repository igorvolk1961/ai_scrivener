from __future__ import annotations

from pathlib import Path
from typing import Any

RETRIEVAL_ROWS = (
    ("cases", "Кейсов"),
    ("answerable_cases", "Answerable"),
    ("no_answer_cases", "No-answer"),
    ("recall_at_k", "Recall@k"),
    ("mrr_at_k", "MRR@k"),
    ("ndcg_at_k", "nDCG@k"),
    ("no_answer_accuracy", "No-answer accuracy (retrieval)"),
    ("latency_p50_ms", "Latency p50, мс"),
    ("latency_p95_ms", "Latency p95, мс"),
)

ANSWER_ROWS = (
    ("found_rate", "Found rate"),
    ("false_refusal_rate", "False refusal rate"),
    ("answers_without_citations", "Ответов без citations"),
    ("citation_precision", "Citation precision"),
    ("citation_recall", "Citation recall"),
    ("citation_accuracy", "Citation accuracy (strict)"),
    ("correctness", "Correctness"),
    ("correctness_cases", "Correctness cases"),
    ("groundedness", "Groundedness"),
    ("groundedness_cases", "Groundedness cases"),
    ("no_answer_precision", "No-answer precision"),
    ("no_answer_recall", "No-answer recall"),
    ("true_no_answer", "Верных отказов"),
    ("false_refusals", "Ложных отказов"),
    ("hallucinated_answers", "Галлюцинаций"),
    ("rerank_fallbacks", "Rerank fallbacks"),
    ("judge_errors", "Ошибок judge"),
    ("errors", "Ошибок выполнения"),
    ("e2e_latency_p50_ms", "E2E p50, мс"),
    ("e2e_latency_p95_ms", "E2E p95, мс"),
)


def write_markdown(report: dict[str, Any], path: Path) -> None:
    run = report.get("run", {})
    retrieval = report.get("retrieval", {})
    answer = report.get("answer", {})
    cases = report.get("cases", [])

    lines = [
        "# Оценка answer-контура RAG",
        "",
        f"- Датасет: `{run.get('dataset', '')}`",
        f"- Коллекция: `{run.get('collection', '')}`",
        f"- Модель ответа: `{run.get('model', '')}`",
        f"- Модель judge: `{run.get('judge_model', '')}`",
        f"- Top-k: {run.get('top_k', '')}",
        f"- Prompt: `{run.get('prompt_version', '')}`",
        "",
        "## Retrieval",
        "",
        "| Метрика | Значение |",
        "|---|---:|",
    ]
    lines.extend(_rows(retrieval, RETRIEVAL_ROWS))
    lines.extend(
        [
            "",
            "## Answer",
            "",
            "| Метрика | Значение |",
            "|---|---:|",
        ]
    )
    lines.extend(_rows(answer, ANSWER_ROWS))

    failures = [
        case
        for case in cases
        if isinstance(case, dict) and (case.get("error") or case.get("judge_error"))
    ]
    if failures:
        lines.extend(["", "## Ошибки и пропуски", ""])
        for case in failures[:20]:
            reason = case.get("error") or case.get("judge_error")
            lines.append(f"- `{case.get('query', '')}`: {reason}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rows(values: dict[str, Any], rows: tuple[tuple[str, str], ...]) -> list[str]:
    result: list[str] = []
    for key, label in rows:
        value = values.get(key)
        result.append(f"| {label} | {_format(value)} |")
    return result


def _format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
