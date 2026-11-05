from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.llm_eval.clients import (
    ChatClient,
    HttpError,
    JsonParseError,
    RagClient,
    ResponseCache,
    extract_json,
)
from tools.llm_eval.metrics import CaseResult, find_rank
from tools.llm_eval.prompts import (
    ANSWER_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    RERANK_REPAIR_SUFFIX,
    RERANK_SYSTEM_PROMPT,
    judge_user_prompt,
)

MAX_CITED_FRAGMENTS = 6
MAX_FRAGMENT_CHARS = 2000


@dataclass(frozen=True)
class EvalCase:
    query: str
    doc_type: str
    filters: dict[str, Any]
    expected_source_ids: tuple[str, ...]
    expected_clauses: tuple[str, ...]
    expected_pages: tuple[int, ...]
    answer_type: str
    must_cite: bool
    no_answer: bool
    difficulty: str
    notes: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvalCase:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("eval case is missing query")
        filters = payload.get("filters")
        return cls(
            query=query,
            doc_type=str(payload.get("doc_type", "")),
            filters=dict(filters) if isinstance(filters, dict) else {},
            expected_source_ids=tuple(
                str(item) for item in _as_list(payload.get("expected_source_ids"))
            ),
            expected_clauses=tuple(str(item) for item in _as_list(payload.get("expected_clauses"))),
            expected_pages=tuple(int(item) for item in _as_list(payload.get("expected_pages"))),
            answer_type=str(payload.get("answer_type", "")),
            must_cite=bool(payload.get("must_cite", False)),
            no_answer=bool(payload.get("no_answer", False)),
            difficulty=str(payload.get("difficulty", "")),
            notes=str(payload.get("notes", "")),
        )

    def expected_pairs(self) -> list[tuple[str, str]]:
        clauses = self.expected_clauses or ("",)
        return [(source_id, clause) for source_id in self.expected_source_ids for clause in clauses]


@dataclass
class Candidate:
    id: str
    source_id: str
    title: str
    doc_type: str
    section: str
    clause: str
    text: str
    page: int | None


@dataclass
class Settings:
    dataset: Path
    output: Path
    rag_url: str
    rag_token: str
    deepseek_base_url: str
    deepseek_api_key: str
    model: str
    judge_model: str
    top_k: int
    candidate_k: int | None
    concurrency: int
    limit: int | None
    timeout: float
    no_rerank: bool
    group_size: int | None
    include_parent: bool | None
    rerank_max_candidates: int
    rerank_text_limit: int
    rerank_json_mode: bool
    no_judge: bool
    no_cache: bool
    cache_dir: Path


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


def run(cases: list[EvalCase], settings: Settings) -> list[CaseResult]:
    cache: ResponseCache | None = None if settings.no_cache else ResponseCache(settings.cache_dir)
    rag = RagClient(settings.rag_url, settings.rag_token, settings.timeout)
    answer_client = ChatClient(
        settings.deepseek_base_url,
        settings.deepseek_api_key,
        settings.model,
        settings.timeout,
        cache,
    )
    judge_client = ChatClient(
        settings.deepseek_base_url,
        settings.deepseek_api_key,
        settings.judge_model,
        settings.timeout,
        cache,
    )

    results: list[CaseResult | None] = [None] * len(cases)
    with ThreadPoolExecutor(max_workers=settings.concurrency) as executor:
        futures = {
            executor.submit(
                evaluate_case,
                case,
                settings,
                rag,
                answer_client,
                judge_client,
            ): index
            for index, case in enumerate(cases)
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = _failed_result(cases[index], error)
            results[index] = result
            print(
                f"[{completed}/{len(cases)}] "
                f"{'NO-ANSWER' if result.no_answer else 'ANSWER'} "
                f"found={result.found} rank={result.retrieval_rank} "
                f"{result.query[:60]}",
                file=sys.stderr,
                flush=True,
            )
    return [result for result in results if result is not None]


def evaluate_case(
    case: EvalCase,
    settings: Settings,
    rag: RagClient,
    answer_client: ChatClient,
    judge_client: ChatClient,
) -> CaseResult:
    retrieval_started = time.perf_counter()
    try:
        response = rag.retrieve(
            case.query,
            case.filters,
            top_k=settings.top_k,
            candidate_k=settings.candidate_k,
            group_size=settings.group_size,
            include_parent=settings.include_parent,
        )
    except (HttpError, OSError) as error:
        return _failed_result(case, error)
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000

    results = response.get("results")
    if not isinstance(results, list):
        results = []
    rank = find_rank(
        results,
        set(case.expected_source_ids),
        set(case.expected_clauses),
    )
    candidates = flatten_candidates(results)
    result = CaseResult(
        query=case.query,
        doc_type=case.doc_type,
        no_answer=case.no_answer,
        expected_sources=list(case.expected_source_ids),
        expected_clauses=list(case.expected_clauses),
        expected_pairs=case.expected_pairs(),
        retrieval_rank=rank,
        retrieval_empty=not results,
        retrieval_ms=retrieval_ms,
    )
    if not candidates:
        result.answer = "В базе знаний не найдено."
        result.e2e_ms = retrieval_ms
        return result

    reranked, rerank_error, rerank_empty = rerank_candidates(
        answer_client,
        case.query,
        candidates,
        enabled=not settings.no_rerank,
        max_candidates=settings.rerank_max_candidates,
        text_limit=settings.rerank_text_limit,
        json_mode=settings.rerank_json_mode,
    )
    if rerank_error is not None:
        result.rerank_fallback = True
        result.rerank_error = rerank_error
        print(f"rerank fallback: {rerank_error}", file=sys.stderr, flush=True)
    result.rerank_empty = rerank_empty

    expected_sources = set(case.expected_source_ids)
    expected_clauses = set(case.expected_clauses)
    result.expected_clause_in_context = any(
        candidate.source_id in expected_sources
        and (not expected_clauses or candidate.clause in expected_clauses)
        for candidate in reranked
    )

    context, allowed, citation_sources = build_context(reranked)
    user_prompt = f"Вопрос: {case.query}\nКонтекст:\n{context}"
    try:
        raw_answer = answer_client.complete(
            ANSWER_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.1,
            max_tokens=2000,
        )
        found, answer_text, raw_citations = parse_answer(raw_answer)
    except (HttpError, JsonParseError, OSError) as error:
        result.error = f"answer: {error}"
        result.e2e_ms = (time.perf_counter() - retrieval_started) * 1000
        return result

    valid_citations, invalid_count = normalize_citations(
        raw_citations,
        allowed,
        citation_sources,
    )
    if found and not valid_citations:
        found = False
        answer_text = "В базе знаний не найдено подтверждённых источников."

    result.found = found
    result.answer = answer_text
    result.citations = valid_citations if found else []
    result.raw_citation_count = len(raw_citations)
    result.invalid_citation_count = invalid_count
    result.raw_citations = [
        {
            "source_id": str(item.get("source_id", "")),
            "clause": str(item.get("clause", "")),
        }
        for item in raw_citations
        if isinstance(item, dict)
    ]
    result.e2e_ms = (time.perf_counter() - retrieval_started) * 1000

    if not case.no_answer and not found:
        result.correctness = 0.0
    elif case.no_answer and not found:
        result.correctness = 1.0
    elif case.no_answer and found:
        result.correctness = 0.0
    elif found and not settings.no_judge:
        try:
            judge = judge_answer(
                judge_client,
                case,
                answer_text,
                cited_fragments(valid_citations, reranked),
            )
            result.correctness = judge["correctness"] / 2
            result.groundedness = judge["groundedness"]
        except (HttpError, JsonParseError, OSError, ValueError) as error:
            result.judge_error = str(error)

    return result


def rerank_candidates(
    client: ChatClient,
    query: str,
    candidates: list[Candidate],
    *,
    enabled: bool,
    max_candidates: int = 30,
    text_limit: int = 1200,
    json_mode: bool = False,
) -> tuple[list[Candidate], str | None, bool]:
    if not enabled or len(candidates) <= 1:
        return candidates, None, False

    selected = candidates[: max(1, max_candidates)]
    payload = {
        "query": query,
        "candidates": [
            {
                "id": candidate.id,
                "source_id": candidate.source_id,
                "clause": candidate.clause,
                "title": candidate.title,
                "text": candidate.text[:text_limit],
            }
            for candidate in selected
        ],
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)
    try:
        raw = client.complete(
            RERANK_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.0,
            max_tokens=2000,
            json_mode=json_mode,
        )
        data = extract_json(raw)
    except (HttpError, JsonParseError, OSError):
        try:
            raw = client.complete(
                RERANK_SYSTEM_PROMPT,
                user_prompt + RERANK_REPAIR_SUFFIX,
                temperature=0.0,
                max_tokens=2000,
                json_mode=json_mode,
            )
            data = extract_json(raw)
        except (HttpError, JsonParseError, OSError) as retry_error:
            return candidates, str(retry_error), False

    ranking = data.get("ranking")
    if not isinstance(ranking, list):
        return candidates, "rerank response has no ranking", False
    if not ranking:
        return candidates, None, True

    by_id = {candidate.id: candidate for candidate in selected}
    ordered: list[Candidate] = []
    used: set[str] = set()
    for item in ranking:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("id", ""))
        candidate = by_id.get(candidate_id)
        if candidate is not None and candidate_id not in used:
            ordered.append(candidate)
            used.add(candidate_id)
    if not ordered:
        return candidates, "rerank returned no known candidate ids", False
    for candidate in selected:
        if candidate.id not in used:
            ordered.append(candidate)
    ordered.extend(candidates[len(selected) :])
    return ordered, None, False


def flatten_candidates(results: list[Any]) -> list[Candidate]:
    candidates: list[Candidate] = []
    index = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        source_id = str(result.get("source_id", ""))
        if not source_id:
            continue
        title = str(result.get("title", "")) or "Без названия"
        metadata = result.get("metadata")
        doc_type = str(metadata.get("doc_type", "")) if isinstance(metadata, dict) else ""
        chunks = result.get("chunks")
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            index += 1
            section = chunk.get("section_path")
            section_text = (
                " → ".join(str(item) for item in section) if isinstance(section, list) else ""
            )
            page = chunk.get("page_start")
            candidates.append(
                Candidate(
                    id=f"K{index}",
                    source_id=source_id,
                    title=title,
                    doc_type=doc_type,
                    section=section_text,
                    clause=str(chunk.get("clause", "")),
                    text=str(chunk.get("text", "")),
                    page=page if isinstance(page, int) else None,
                )
            )
    return candidates


def build_context(candidates: list[Candidate]) -> tuple[str, set[str], dict[str, str]]:
    lines: list[str] = []
    allowed: set[str] = set()
    sources: dict[str, str] = {}
    for index, candidate in enumerate(candidates, start=1):
        label = f"S{index}"
        header = f"[{label}] Документ: {candidate.title}"
        if candidate.doc_type:
            header += f"; вид: {candidate.doc_type}"
        if candidate.section:
            header += f"; раздел: {candidate.section}"
        if candidate.clause:
            header += f"; пункт: {candidate.clause}"
        lines.append(f"{header}\n{candidate.text}")
        allowed.add(candidate.source_id)
        allowed.add(label)
        sources[candidate.source_id] = candidate.source_id
        sources[label] = candidate.source_id
        if candidate.clause:
            allowed.add(f"{candidate.source_id}|{candidate.clause}")
            allowed.add(f"{label}|{candidate.clause}")
            sources[f"{candidate.source_id}|{candidate.clause}"] = candidate.source_id
            sources[f"{label}|{candidate.clause}"] = candidate.source_id
    return "\n".join(lines), allowed, sources


def normalize_citations(
    raw_citations: list[Any],
    allowed: set[str],
    sources: dict[str, str],
) -> tuple[list[dict[str, str]], int]:
    valid: list[dict[str, str]] = []
    invalid = 0
    seen: set[tuple[str, str]] = set()
    for item in raw_citations:
        if not isinstance(item, dict):
            invalid += 1
            continue
        raw_id = str(item.get("source_id", "")).strip()
        clause = str(item.get("clause", "")).strip()
        if not raw_id:
            invalid += 1
            continue
        allowed_key = f"{raw_id}|{clause}" if clause else raw_id
        source_id = sources.get(raw_id)
        if source_id is None or allowed_key not in allowed:
            invalid += 1
            continue
        key = (source_id, clause)
        if key in seen:
            continue
        seen.add(key)
        valid.append({"source_id": source_id, "clause": clause})
    return valid, invalid


def parse_answer(raw: str) -> tuple[bool, str, list[Any]]:
    data = extract_json(raw)
    found = data.get("found") is True
    answer = str(data.get("answer", "")).strip()
    citations = data.get("citations")
    return found, answer, citations if isinstance(citations, list) else []


def cited_fragments(
    citations: list[dict[str, str]],
    candidates: list[Candidate],
) -> str:
    fragments: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for citation in citations:
        source_id = citation["source_id"]
        clause = citation.get("clause", "")
        for candidate in candidates:
            if candidate.source_id != source_id:
                continue
            if clause and candidate.clause != clause:
                continue
            key = (candidate.source_id, candidate.clause, candidate.text[:80])
            if key in seen:
                continue
            seen.add(key)
            fragments.append(
                f"[{len(fragments) + 1}] source_id={candidate.source_id}; "
                f"clause={candidate.clause}\n"
                f"{candidate.text[:MAX_FRAGMENT_CHARS]}"
            )
            if len(fragments) >= MAX_CITED_FRAGMENTS:
                return "\n\n".join(fragments)
    return "\n\n".join(fragments)


def judge_answer(
    client: ChatClient,
    case: EvalCase,
    answer: str,
    fragments: str,
) -> dict[str, float]:
    reference = (
        f"Тип документа: {case.doc_type or 'не задан'}\n"
        f"Ожидаемые пункты: {', '.join(case.expected_clauses) or 'не заданы'}\n"
        f"Ключевые факты: {case.notes or 'не заданы'}"
    )
    user_prompt = judge_user_prompt(case.query, reference, answer, fragments)
    data: dict[str, Any] | None = None
    for attempt in range(2):
        prompt = (
            user_prompt
            if attempt == 0
            else f"{user_prompt}\n\nВерни только JSON указанной схемы, без markdown и пояснений."
        )
        raw = client.complete(
            JUDGE_SYSTEM_PROMPT,
            prompt,
            temperature=0.0,
            max_tokens=1000,
        )
        try:
            data = extract_json(raw)
            break
        except JsonParseError:
            if attempt == 1:
                raise

    if data is None:
        raise ValueError("judge returned no JSON")
    correctness = _as_int(data.get("correctness"))
    groundedness = _as_float(data.get("groundedness"))
    if correctness not in (0, 1, 2):
        raise ValueError("judge returned invalid correctness")
    if groundedness is None or not 0.0 <= groundedness <= 1.0:
        raise ValueError("judge returned invalid groundedness")
    return {"correctness": float(correctness), "groundedness": groundedness}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _failed_result(case: EvalCase, error: Exception) -> CaseResult:
    return CaseResult(
        query=case.query,
        doc_type=case.doc_type,
        no_answer=case.no_answer,
        expected_sources=list(case.expected_source_ids),
        expected_clauses=list(case.expected_clauses),
        expected_pairs=case.expected_pairs(),
        error=str(error),
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
