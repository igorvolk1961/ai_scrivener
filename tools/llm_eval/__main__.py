from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.llm_eval.clients import load_env_file
from tools.llm_eval.metrics import aggregate
from tools.llm_eval.prompts import PROMPT_VERSION
from tools.llm_eval.report import write_markdown
from tools.llm_eval.run import Settings, load_cases, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm_eval",
        description="Оценка answer-контура RAG: retrieve → rerank → DeepSeek → citations → judge.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("rag-service/eval/golden/knowledge.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/llm-eval/knowledge-answer-eval.json"),
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--rag-env-file",
        type=Path,
        default=Path("rag-service/.env"),
    )
    parser.add_argument("--rag-url")
    parser.add_argument("--model")
    parser.add_argument("--judge-model")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int)
    parser.add_argument("--group-size", type=int)
    parser.add_argument(
        "--include-parent",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--skip-listwise-if-rag-rerank",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--rerank-max-candidates", type=int, default=15)
    parser.add_argument("--rerank-text-limit", type=int, default=1200)
    parser.add_argument(
        "--rerank-json-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("artifacts/llm-eval/cache"),
    )
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env_file(args.env_file)
    load_env_file(args.rag_env_file)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    rag_token = os.environ.get("RAG_SERVICE_TOKEN", "").strip()
    if not api_key:
        print("error: DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2
    if not rag_token:
        print("error: RAG_SERVICE_TOKEN is not set", file=sys.stderr)
        return 2

    model = args.model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    settings = Settings(
        dataset=args.dataset,
        output=args.output,
        rag_url=args.rag_url or os.environ.get("RAG_URL", "http://127.0.0.1:8080"),
        rag_token=rag_token,
        deepseek_base_url=base_url,
        deepseek_api_key=api_key,
        model=model,
        judge_model=args.judge_model or model,
        top_k=args.top_k,
        candidate_k=args.candidate_k,
        group_size=args.group_size,
        include_parent=args.include_parent,
        concurrency=max(1, args.concurrency),
        limit=args.limit,
        timeout=args.timeout,
        skip_listwise_if_rag_rerank=args.skip_listwise_if_rag_rerank,
        no_rerank=args.no_rerank,
        rerank_max_candidates=max(1, args.rerank_max_candidates),
        rerank_text_limit=max(1, args.rerank_text_limit),
        rerank_json_mode=args.rerank_json_mode,
        no_judge=args.no_judge,
        no_cache=args.no_cache,
        cache_dir=args.cache_dir,
    )

    cases = load_cases(settings.dataset)
    if settings.limit is not None:
        cases = cases[: settings.limit]
    if not cases:
        print("error: no eval cases", file=sys.stderr)
        return 2

    print(
        f"running {len(cases)} cases: model={settings.model} "
        f"judge={settings.judge_model} concurrency={settings.concurrency}",
        file=sys.stderr,
    )
    results = run(cases, settings)
    metrics = aggregate(results, settings.top_k)
    report: dict[str, Any] = {
        "run": {
            "timestamp": datetime.now(UTC).isoformat(),
            "dataset": str(settings.dataset),
            "dataset_sha256": _sha256(settings.dataset),
            "rag_url": settings.rag_url,
            "model": settings.model,
            "judge_model": settings.judge_model,
            "top_k": settings.top_k,
            "candidate_k": settings.candidate_k,
            "group_size": settings.group_size,
            "include_parent": settings.include_parent,
            "prompt_version": PROMPT_VERSION,
            "rerank": not settings.no_rerank,
            "skip_listwise_if_rag_rerank": settings.skip_listwise_if_rag_rerank,
            "judge": not settings.no_judge,
        },
        "retrieval": metrics["retrieval"],
        "answer": metrics["answer"],
        "cases": [result.to_dict() for result in results],
    }
    settings.output.parent.mkdir(parents=True, exist_ok=True)
    settings.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_output = args.markdown_output or settings.output.with_suffix(".md")
    write_markdown(report, markdown_output)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"report: {settings.output}", file=sys.stderr)
    print(f"markdown: {markdown_output}", file=sys.stderr)
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
