# RAG retrieval eval

Каждая строка датасета — JSON-объект:

```json
{
  "query": "порядок утверждения штатного расписания",
  "filters": {"source_types": ["template_internal"]},
  "expected_source_ids": ["uuid-шаблона"],
  "expected_clauses": ["4.2.1"],
  "no_answer": false
}
```

Поля:

- `query` — обязательный запрос;
- `filters` — фильтры `/v1/retrieve`;
- `expected_source_ids` — ожидаемые `source_id` документов;
- `expected_clauses` — ожидаемые номера пунктов;
- `no_answer` — запрос без правильного ответа; успех, если retrieval вернул пусто.

Запуск:

```bash
uv run --project rag-service python -m rag_service.eval \
  --dataset rag-service/eval/golden/templates.jsonl \
  --top-k 10 \
  --output artifacts/rag-eval/templates.json
```

Метрики: Recall@k, MRR@k, nDCG@k, no-answer accuracy, latency p50/p95. Формулы, ограничения и answer-метрики — `docs/rag-evaluation.md`.

## Knowledge golden set (2026-11-05)

`rag-service/eval/golden/knowledge.jsonl` — первый срез по 15 типам документов и 30 материалам пилотной коллекции `ai_scrivener_knowledge_pilot_1793864097`:

- 70 кейсов: 60 answerable + 10 no-answer (10–15% по плану);
- `expected_source_ids` — `sha256` из манифеста `2026-11-04.jsonl` (sha256 манифеста `24ca1d4f...`);
- для answerable заданы `filters.doc_types`, `expected_clauses` и `expected_pages`;
- `doc_type`, `answer_type`, `difficulty`, `notes` — справочные поля для ревью, eval их не использует.

Baseline на пилотной коллекции: Recall@10 = 1.000, MRR@10 = 0.983, nDCG@10 = 0.988, no-answer accuracy = 0.000. Прогон без `filters.doc_types` даёт те же метрики, то есть запросы сами по себе различают документы. Нулевая no-answer accuracy ожидаема при `search_min_score = 0.0`: порог отсечения нерелевантных результатов — отдельная задача. После полной индексации набор расширяется на все типы корпуса.
