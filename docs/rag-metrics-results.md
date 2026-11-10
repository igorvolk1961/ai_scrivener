# Собранные метрики RAG

> **Ограничение:** модели GigaChat (`GigaChat/GigaChat-3-Pro`, `ai-sage/GigaChat3-10B-A1.8B`) использовались только в исторических прогонах. По указанию владельца продукта в дальнейшем их не использовать до явного указания. Все новые эксперименты — DeepSeek, Cloud.ru embeddings и BAAI.

Дата: 2026-11-05
Статус: сводка всех прогонов; часть прогонов промежуточная и не используется для выбора production-конфигурации.

## 1. Термины и как читать

- **Кейс** — один вопрос golden set с ожидаемыми `source_id`/`clause`.
- **Прогон** — одна конфигурация пайплайна (модель, реранкер, настройки retrieval).
- `70 кейсов` = 60 answerable + 10 no-answer; `20 кейсов` — срез answerable.
- Метрики качества считаются по answerable-кейсам; no-answer precision/recall — только по no-answer.
- **p95** на 20–70 кейсах нестабилен: один долгий LLM-вызов может доминировать. Сравнивать нужно p50 и этапы, а не только e2e p95.
- Часть e2e-замеров сделана с локальным кэшем ответов; такие значения (например, p50 178 мс в pre-chunk baseline) не отражают production latency. Для latency нужны прогоны с `--no-cache`.
- **RAG BAAI** — cross-encoder `BAAI/bge-reranker-v2-m3` внутри `/v1/retrieve` (Cloud.ru, 15 кандидатов).
- **Listwise** — отдельный LLM-вызов `РеранкФрагменты` (DeepSeek или GigaChat).
- В одном пайплайне должен быть **один** реранкер. Прогоны с `BAAI + listwise` — двойное реранжирование, только для диагностики.

## 2. Политика окружений

| Окружение | Answer/rerank LLM | Reranker | Статус |
|---|---|---|---|
| Production (цель) | `GigaChat/GigaChat-3-Pro` | `BAAI/bge-reranker-v2-m3` (568M, foreign <1B) | соответствует правилу «без зарубежных >1B» |
| Development | `deepseek-chat` / `deepseek-v4-flash` | `BAAI/bge-reranker-v2-m3` | дешевле; foreign >1B допустим только вне production |
| Текущий RAG-сервис | Cloud.ru embeddings `ai-sage/Giga-Embeddings-instruct-480M` (480M) | BAAI **включён** (15, timeout 3 с) | dev-контур собран |
| Текущий 1С | `АИС_МодельИИ` пустая → `deepseek-chat`; ключ LLM только в `.env` agent-service | listwise только если `diagnostics.rerank=false` | dev-контур собран |

Важно: целевая production-пара **BAAI + GigaChat-3-Pro** ещё не измерена одним прогоном. Есть две ближайшие точки: `BAAI + DeepSeek answer` (dev) и `GigaChat-3-Pro listwise + answer` (production без BAAI).

## 3. Retrieval-метрики

Сводка по `artifacts/rag-eval/*.json` (агрегаты пересчитаны из per-case отчётов):

| Файл | Кейсов | Answerable | Recall@10 | MRR@10 | nDCG@10 | No-answer acc | p50 / p95, мс |
|---|---:|---:|---:|---:|---:|---:|---:|
| `knowledge-baseline.json` | 70 | 60 | 1.0000 | 0.9833 | 0.9877 | 0.0 | 138.1 / 267.0 |
| `knowledge-cloudru-rerank.json` | 70 | 60 | 1.0000 | 1.0000 | 1.0000 | 0.0 | 885.6 / 1096.1 |
| `knowledge-cloudru-rerank15.json` | 70 | 60 | 1.0000 | 1.0000 | 1.0000 | 0.0 | 374.8 / 536.6 |
| `knowledge-cloudru.json` | 70 | 60 | 1.0000 | 1.0000 | 1.0000 | 0.0 | 134.9 / 212.1 |
| `knowledge-full-cloudru.json` | 70 | 60 | 1.0000 | 0.9833 | 0.9877 | 0.0 | 609.3 / 903.2 |
| `knowledge-production-cloudru.json` | 70 | 60 | 1.0000 | 1.0000 | 1.0000 | 0.0 | 136.4 / 179.6 |
| `knowledge-production-full.json` | 70 | 60 | 1.0000 | 0.9833 | 0.9877 | 0.0 | 416.8 / 601.8 |
| `knowledge-rechunk.json` | 70 | 60 | 1.0000 | 1.0000 | 1.0000 | 0.0 | 137.9 / 283.1 |

Примечания:

- `knowledge-baseline.json` — старый GigaChat-пилот, 30 документов; не сравнивать напрямую с Cloud.ru.
- `knowledge-rechunk.json` — rechunk без полного OCR.
- `knowledge-cloudru*.json` — полная переиндексация 30 документов с PaddleOCR и Cloud.ru embeddings.
- `knowledge-cloudru-rerank.json` — BAAI на 50 кандидатах; `knowledge-cloudru-rerank15.json` — BAAI на 15.
- Retrieval p95 в answer-прогонах может отличаться от retrieval-прогонов из-за retry/нагрузки; см. колонку e2e ниже.

## 4. Answer-метрики

Все собранные answer-прогоны. `Rerank` = listwise-вызов; `RAG BAAI` = cross-encoder внутри retrieval.

| Прогон | Модель | Rerank | RAG BAAI | Кейсов | found | cit prec | cit rec | cit acc | corr | ground | no-ans prec | e2e p50 / p95, мс | Примечание |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Pre-chunk baseline: DeepSeek, old citations | DeepSeek | listwise | no | 70 | 0.4167 | 0.3553 | 0.4167 | 0.8000 | 0.3661 | 0.9843 | 0.2222 | 178.6210 / 15511.8688 | 30 docs, chunker bug |
| Rechunk: DeepSeek, old citations, JSON off | DeepSeek | listwise | no | 70 | 0.5000 | 0.4568 | 0.5000 | 0.8000 | 0.4655 | 0.9654 | 0.2500 | 11815.1839 / 48326.5679 | chunker fix, citations still objects |
| Rechunk: DeepSeek, old citations, JSON mode | DeepSeek | listwise | no | 70 | 0.5000 | 0.3977 | 0.5000 | 0.8667 | 0.4831 | 0.9655 | 0.2500 | 8281.6240 / 18288.3449 | rerank fallback fixed |
| Rechunk: group_size=5, old citations | DeepSeek | listwise | no | 70 | 0.6167 | 0.4713 | 0.5833 | 0.8649 | 0.5818 | 0.9891 | 0.3030 | 7037.4215 / 98427.7749 | context fix |
| Rechunk: group_size=5, labels-only | DeepSeek | listwise | no | 70 | 0.9667 | 0.9759 | 0.9333 | 0.9655 | 0.9386 | 0.9982 | 0.8333 | 5687.2109 / 10877.1070 | main quality jump |
| Rechunk: group_size=10, labels-only | DeepSeek | listwise | no | 70 | 0.9500 | 0.8750 | 0.9333 | 0.9825 | 0.9298 | 1.0000 | 0.7692 | 7583.1671 / 43025.2275 | worse than g5 |
| CloudRu full reindex: DeepSeek listwise | DeepSeek | listwise | no | 70 | 0.9333 | 0.8111 | 0.8333 | 0.8929 | 0.9123 | 1.0000 | 0.7143 | 6201.2744 / 13129.0970 | production baseline on CloudRu |
| CloudRu full: BAAI 50 + DeepSeek listwise | DeepSeek | listwise | yes | 70 | 0.9500 | 0.8710 | 0.8833 | 0.9298 | 0.9298 | 1.0000 | 0.7692 | 8313.4661 / 39112.8319 | double rerank; not production |
| CloudRu full: BAAI 15 + DeepSeek listwise | DeepSeek | listwise | yes | 70 | 0.9492 | 0.8587 | 0.8644 | 0.9107 | 0.9322 | 0.9964 | 0.7692 | 7082.3390 / 23935.8093 | double rerank; fair candidate count |
| CloudRu full: BAAI 15 only | DeepSeek | none | yes | 70 | 0.9500 | 0.8602 | 0.8667 | 0.9123 | 0.9474 | 1.0000 | 0.7692 | 2906.0611 / 52338.3613 | development candidate |
| Dev: BAAI 15 + DeepSeek answer, full corpus | DeepSeek | none | yes | 70 | 0.9492 | 0.8764 | 0.8305 | 0.8750 | 0.9182 | 1.0000 | 0.7692 | 3089.6 / 6974.4 | full 170 docs, 34 506 chunks; 1 error |
| Dev: BAAI 15 + DeepSeek answer, timeout 3s | DeepSeek | none | yes | 70 | 0.9500 | 0.8605 | 0.8667 | 0.9123 | 0.9375 | 0.9991 | 0.7692 | 3063.9 / 10459.0 | dev target; 68/70 BAAI, 2 listwise fallback |
| CloudRu full: GigaChat-3-Pro listwise | GigaChat-3-Pro | listwise | no | 70 | 0.9833 | 0.8804 | 0.8833 | 0.8983 | 0.9417 | 0.9536 | 0.9091 | 3179.7440 / 6218.0755 | production candidate without BAAI |
| Paired 20: DeepSeek listwise | DeepSeek | listwise | no | 20 | 1.0000 | 0.8182 | 0.8000 | 0.8000 | 1.0000 | 0.9947 | — | 5507.7440 / 10753.3315 | same 20 cases |
| Paired 20: BAAI 15 only | DeepSeek | none | yes | 20 | 1.0000 | 0.9032 | 0.8500 | 0.8500 | 1.0000 | 1.0000 | — | 3400.6920 / 95163.3861 | same 20 cases |
| Paired 20: GigaChat3-10B listwise | GigaChat3-10B | listwise | no | 20 | 0.6500 | 0.7368 | 0.4500 | 0.6923 | 0.5750 | 0.8846 | 0.0000 | 1347.8100 / 1830.1324 | weak domestic model |
| Paired 20: GigaChat-3-Pro listwise | GigaChat-3-Pro | listwise | no | 20 | 1.0000 | 0.8056 | 0.8000 | 0.8000 | 0.9750 | 0.9908 | — | 3134.1595 / 18598.0027 | same 20 cases |
| Arm A (10): DeepSeek listwise | DeepSeek | listwise | no | 10 | 0.9000 | 0.6471 | 0.7000 | 0.7778 | 0.8333 | 1.0000 | 0.0000 | 6403.7929 / 12557.7175 | split experiment, not used |
| Arm B (10): BAAI 15 only | DeepSeek | none | yes | 10 | 1.0000 | 0.9375 | 0.9000 | 0.9000 | 1.0000 | 1.0000 | — | 2388.1840 / 4834.8448 | split experiment, different cases |
| Arm A (10): BAAI 15 only | DeepSeek | none | yes | 10 | 1.0000 | 0.8125 | 0.8000 | 0.8000 | 1.0000 | 1.0000 | — | 3266.2526 / 93864.3472 | paired check on arm A |

## 5. Ключевые сравнения

### 5.1. Один и тот же набор 70 кейсов: DeepSeek listwise vs GigaChat-3-Pro listwise

| Метрика | DeepSeek | GigaChat-3-Pro |
|---|---:|---:|
| found_rate | 0.9333 | **0.9833** |
| false_refusals | 4 | **1** |
| citation_accuracy | 0.8929 | **0.8983** |
| correctness | 0.9123 | **0.9417** |
| no_answer_precision | 0.7143 | **0.9091** |
| e2e p50 / p95 | 6.20 / 13.13 с | **3.18 / 6.22 с** |

GigaChat-3-Pro — domestic-модель, соответствует production-политике и по этим метрикам лучше DeepSeek. Это прогон **без BAAI** (listwise GigaChat).

### 5.2. Один и тот же набор 70 кейсов: DeepSeek listwise vs BAAI-only

| Метрика | DeepSeek listwise | BAAI-only + DeepSeek answer |
|---|---:|---:|
| found_rate | 0.9333 | **0.9500** |
| citation_accuracy | 0.8929 | **0.9123** |
| correctness | 0.9123 | **0.9474** |
| no_answer_precision | 0.7143 | **0.7692** |
| e2e p50 / p95 | 6.20 / 13.13 с | **2.91** / 52.34 с |

BAAI-only лучше по качеству и p50, но имеет высокий собственный retrieval p95 (16.7 с) и e2e-хвост. E2E p95 не является метрикой реранкера; для решения нужен stage-level замер с таймаутом/fallback.

### 5.3. Paired 20 кейсов, постадийно

| Этап | DeepSeek listwise | BAAI-only + DeepSeek |
|---|---:|---:|
| retrieval p50 / p95 | 317 / 496 мс | 700 / 983 мс |
| listwise p50 / p95 | 4 368 / 6 703 мс | — |
| answer p50 / p95 | 2 295 / 5 563 мс | 2 286 / 3 919 мс |
| e2e p50 / p95 | 6 880 / 12 464 мс | 8 957 / 14 107 мс |
| контекст, символов p50 | 13 523 | 13 214 |

Answer-стадия в обоих вариантах практически одинаковая; разница e2e — дополнительный retrieval-вызов и изменение входа listwise (в варианте с BAAI listwise отсутствует).

### 5.4. GigaChat3-10B: полные сохранённые метрики

Модель: `ai-sage/GigaChat3-10B-A1.8B` (domestic, 10B total / 1.8B active).
Датасет: тот же paired-набор из 20 answerable-кейсов (`artifacts/eval-20.jsonl`).
Артефакт: `artifacts/llm-eval/paired-20-gigachat3.json`.

| Метрика | Значение |
|---|---:|
| Retrieval Recall@10 / MRR@10 / nDCG@10 | 1.0000 / 1.0000 / 1.0000 |
| Retrieval p50 / p95 | 191 / 442 мс |
| found_rate | 0.6500 |
| false_refusals | 7 |
| expected_clause_in_context | 0.8000 |
| false_refusals_with_context | 7 |
| citation_precision | 0.7368 |
| citation_recall | 0.4500 |
| citation_accuracy | 0.6923 |
| correctness | 0.5750 |
| groundedness | 0.8846 |
| no_answer_precision | 0.0000 (в наборе нет no-answer-кейсов) |
| e2e p50 / p95 | 1.35 / 1.83 с |
| rerank_fallbacks / empty rankings | 0 / 0 |
| judge_errors | 0 |

Сравнение на тех же 20 кейсах:

| Модель | found | cit acc | correctness | e2e p50 / p95 |
|---|---:|---:|---:|---:|
| DeepSeek listwise | 1.0000 | 0.8000 | 1.0000 | 5.51 / 10.75 с |
| GigaChat-3-Pro listwise | 1.0000 | 0.8000 | 0.9750 | 3.13 / 18.60 с |
| GigaChat3-10B listwise | 0.6500 | 0.6923 | 0.5750 | 1.35 / 1.83 с |
| BAAI 15 only + DeepSeek answer | 1.0000 | 0.8500 | 1.0000 | 3.40 / 95.16 с |

GigaChat3-10B самый быстрый, но качество существенно ниже: 7 ложных отказов и citation recall 0.45. Для production не выбран. Полный прогон на 70 кейсах для этой модели не выполнялся — только 20-кейсовый paired-срез; это отмечено в разделе 7.

### 5.5. Dev-пайплайн: BAAI 15 + DeepSeek answer, timeout 3 с

Артефакт: `artifacts/llm-eval/dev-baai-deepseek-full.json`.
Условия: RAG BAAI включён (`rerank_candidate_limit=15`, `rerank_batch_size=15`, `rerank_timeout_seconds=3`), 1С-подобная логика: если `/v1/retrieve` вернул `diagnostics.rerank=true`, listwise не вызывается; иначе — fallback на DeepSeek listwise.

| Метрика | Значение |
|---|---:|
| found_rate | 0.9500 |
| false_refusals | 3 |
| expected_clause_in_context | 0.9167 |
| citation_precision | 0.8605 |
| citation_recall | 0.8667 |
| citation_accuracy | 0.9123 |
| correctness | 0.9375 |
| groundedness | 0.9991 |
| no_answer_precision | 0.7692 |
| retrieval p50 / p95 | 658 / 1125 мс |
| e2e p50 / p95 | 3064 / 10459 мс |
| BAAI успешно / listwise fallback | 68 / 2 |

Это лучше DeepSeek listwise по found/cit/correctness и p50, а таймаут убрал прежний retrieval p95 16.7 с. Остаточные 3 ложных отказа:

1. «Каким международным стандартам соответствует ГОСТ 9733.4-83?» — нужный п. 4 не попал в контекст;
2. два вопроса по учебнику логистики — в контексте только заголовки разделов 17.2/17.4, без самого перечня. Это ограничение extraction/полноты корпуса.

Из-за них citation_accuracy 0.912 < 0.95 и no_answer_precision 0.769 < 0.90. Для исправления нужны: контекст/ранжирование для п. 4 и полная переиндексация книги с OCR/извлечением содержимого (п. 6).

## 6. Промежуточные и непригодные для выбора прогоны

- **Pre-chunk baseline** (`knowledge-answer-eval.json`): chunker терял пункты, citations в старом формате; found 0.4167, correctness 0.3661. Не использовать как оценку модели.
- **Rechunk без labels-only** (`knowledge-answer-rechunk.json`, `knowledge-answer-g5.json`): ложные отказы из-за citations; показывает эффект контекста, но не финальное качество.
- **`group_size=10`** (`knowledge-answer-labels-g10.json`): полное покрытие пункта, но found/citation precision и latency хуже g5.
- **Двойное реранжирование** (`knowledge-answer-cloudru-rerank*.json`): BAAI + listwise. Это не production-конфигурация; качество/латентность не годятся для выбора одного реранкера.
- **Split 10/10** (`arm-*.json`): разные кейсы в группах, сравнение смешивает сложность; не использовать.
- **Smoke** (`smoke*.json`, `model-flash.json`): 1–3 кейса, только проверка пайплайна.

## 7. Что ещё не измерено

1. Целевая production-пара **BAAI 15 + GigaChat-3-Pro answer** (без DeepSeek listwise) — нужен полный paired-прогон.
2. BAAI cross-encoder с таймаутом/fallback на RRF: текущий stage p95 16.7 с; без ограничения хвоста production-риск.
3. Golden set на всех 68 типах и полном корпусе 599 документов.
4. No-answer threshold для retrieval: `search_min_score=0.0`, retrieval no-answer accuracy 0.0.
5. Полная переиндексация после последних изменений чанкера/конфига (текущая Cloud.ru-коллекция — 30 документов, 5538 чанков).
6. Полный 70-кейсовый прогон `GigaChat3-10B` (есть только 20-кейсовый paired; см. 5.4).
7. Полная переиндексация 170 уникальных документов завершена: 170/170, 34 506 чанков, коллекция `cloudru_full_v1_1793918359`. Alias `ai_scrivener_knowledge_current` переключён на неё; production retrieval: Recall 1.0, MRR 0.9833, nDCG 0.9877, p50/p95 417/602 мс. Полный answer-eval (dev BAAI+DeepSeek): found 0.9492, citation_accuracy 0.8750, correctness 0.9182, no-answer_precision 0.7692, e2e p50/p95 3.09/6.97 с. Rollback alias: `cloudru_pilot_v1_1793908370`.

## 8. Артефакты

- `artifacts/rag-eval/*.json` — retrieval-прогоны;
- `artifacts/llm-eval/*.json` — answer-прогоны;
- `artifacts/rag-reindex-cloudru/report.json` — отчёт переиндексации 30/30;
- `rag-service/eval/golden/knowledge.jsonl` — golden set v0 (70 кейсов, 15 типов, 30 документов);
- `docs/rag-evaluation.md` — формулы и методика;
- `plans/2026-11-05-rag-quality-next.md` — план следующих шагов.
