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

Метрики: Recall@k, MRR@k, nDCG@k, no-answer accuracy, latency p50/p95.
