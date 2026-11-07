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

## Документы документооборота (scope=documents)

Для документов используется тот же формат с дополнительными полями:

```json
{
  "query": "какая редакция приказа действует сейчас",
  "scope": "documents",
  "filters": {
    "source_types": ["document_internal"],
    "acl_principals": ["user:...", "position:...", "all"]
  },
  "expected_source_ids": ["uuid-текущей-редакции"],
  "expected_clauses": ["2.1"],
  "stale_source_ids": ["uuid-старой-редакции"],
  "forbidden_source_ids": ["uuid-недоступного-документа"],
  "no_answer": false
}
```

Поля:

- `scope` — `knowledge` (по умолчанию) или `documents`;
- `stale_source_ids` — `source_id` старых редакций; попадание любого из них в top-k означает утечку устаревшей версии;
- `forbidden_source_ids` — `source_id` документов, недоступных пользователю из `filters.acl_principals`; попадание любого из них означает утечку ACL.

Дополнительные метрики в отчёте:

| Метрика | Знаменатель | Цель |
|---|---|---:|
| `stale_version_leak_rate` | кейсы с непустым `stale_source_ids` | 0 |
| `acl_leak_rate` | кейсы с непустым `forbidden_source_ids` | 0 |
| `current_version_accuracy` | documents-кейсы с `expected_source_ids` и `no_answer=false`; top-1 должен быть ожидаемым | ≥ 0,85 |

Устаревание определяется по `source_id` из `stale_source_ids`, по `is_current=false` в результате/чанке и по `status=superseded` в metadata. ACL-утечка — только по `forbidden_source_ids`: harness проверяет, что сервис не вернул документ, который golden set считает недоступным.

Запуск documents-набора:

```bash
uv run --project rag-service python -m rag_service.eval \
  --dataset rag-service/eval/golden/documents.jsonl \
  --top-k 10 \
  --output artifacts/rag-eval/documents.json
```

Answer-eval (`tools/llm_eval`) читает поле `scope` из той же строки и передаёт его в `/v1/retrieve`; для `scope=documents` в `filters` должны быть `acl_principals` пользователя, иначе сервис вернёт пустую выдачу.

```bash
uv run python -m tools.llm_eval \
  --dataset rag-service/eval/golden/documents.jsonl \
  --concurrency 4 \
  --no-cache \
  --env-file /home/igorvolk/PycharmProjects/ai_scrivener/.env \
  --rag-env-file /home/igorvolk/PycharmProjects/ai_scrivener/rag-service/.env \
  --output artifacts/llm-eval/documents-answer-eval.json
```

## Knowledge golden set (2026-11-05)

`rag-service/eval/golden/knowledge.jsonl` — первый срез по 15 типам документов и 30 материалам пилотной коллекции `ai_scrivener_knowledge_pilot_1793864097`:

- 70 кейсов: 60 answerable + 10 no-answer (10–15% по плану);
- `expected_source_ids` — `sha256` из манифеста `2026-11-04.jsonl` (sha256 манифеста `24ca1d4f...`);
- для answerable заданы `filters.doc_types`, `expected_clauses` и `expected_pages`;
- `doc_type`, `answer_type`, `difficulty`, `notes` — справочные поля для ревью, eval их не использует.

Baseline на пилотной коллекции: Recall@10 = 1.000, MRR@10 = 0.983, nDCG@10 = 0.988, no-answer accuracy = 0.000. Прогон без `filters.doc_types` даёт те же метрики, то есть запросы сами по себе различают документы. Нулевая no-answer accuracy ожидаема при `search_min_score = 0.0`: порог отсечения нерелевантных результатов — отдельная задача. После полной индексации набор расширяется на все типы корпуса.
