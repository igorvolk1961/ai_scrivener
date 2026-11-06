# RAG: план доведения качества Q&A

Дата: 2026-11-05
Статус: рабочий план после пилотного eval; alias не переключался.

Связанные документы:

- `plans/2026-11-04-effective-rag.md` — основной план RAG-контура;
- `docs/rag-evaluation.md` — метрики, формулы и результаты прогонов;
- `rag-service/eval/golden/knowledge.jsonl` — golden set v0;
- `tools/llm_eval` — answer-eval;
- `config/parameters.yaml` — `group_size=5`, `include_parent=false`.

## 1. Текущее состояние

Пилот: 30 документов, 15 типов, golden set 70 кейсов (60 answerable + 10 no-answer).

Проверенная коллекция: `ai_scrivener_knowledge_pilot_v2b_1793897131` — rechunk старых чанков, таблицы сохранены, OCR и extraction не повторялись. Alias `ai_scrivener_knowledge_current` всё ещё указывает на старую пилотную коллекцию; временный сервис на 8081 остановлен.

Последний полный eval (`group_size=5`, без parent, citations только метками `[S1]`):

| Метрика | Значение | Цель |
|---|---:|---:|
| Recall@10 / MRR@10 / nDCG@10 | 1.000 / 1.000 / 1.000 | ≥ 0.85 / — / ≥ 0.70 |
| found_rate | 0.9667 | — |
| false_refusals | 2 | — |
| citation_precision | 0.9759 | — |
| citation_accuracy | 0.9655 | ≥ 0.95 |
| correctness | 0.9386 | — |
| groundedness | 0.9982 | — |
| no_answer_precision | 0.8333 | ≥ 0.90 |
| no_answer_recall | 1.0000 | — |
| rerank_fallbacks | 0 | — |
| e2e p50 / p95 | 5.7 / 10.9 с | p95 < 3 с |

Последняя попытка полной переиндексации: 30 документов, 4 проиндексировано, 26 упало на `POST /v1/index/chunks` из-за `GigaChat 402 Payment Required`. Неполная коллекция `ai_scrivener_knowledge_pilot_v3_*` удалена; alias не менялся. Текущая RAG-коллекция `v2b` остаётся проверенным кандидатом, но retrieval сейчас недоступен из-за квоты эмбеддингов.

Остаточные проблемы:

- 2 ложных отказа по учебнику Гаджинского: в контексте есть только заголовки разделов 17.2/17.4, нет самого перечня. Это ограничение extraction/полноты корпуса, а не `group_size`.
- `no_answer_precision` 0.833 из-за этих же 2 ложных отказов.
- Латентность выше цели: rerank + ответ модели дают p95 ≈ 11 с.
- Golden set покрывает 15 из 68 типов и 30 из 599 документов.
- Метрики сняты на rechunk-коллекции, а не на полной переиндексации с Paddle/OCR.
- В 1С активный промпт в базе может быть старой версии; seed обновлён, runtime-инструкция добавлена, но БД нужно проверить.

### Решение по реранкеру

**GigaChat не использовать до явного указания владельца продукта.** Метрики GigaChat-3-Pro и GigaChat3-10B в этом плане и в `docs/rag-metrics-results.md` — исторические; новые прогоны с ними не запускать. Текущий дефолт 1С — `deepseek-chat`; модель задаётся `Константа.АИС_МодельИИ`.

Dev-контур собран: BAAI 15 + DeepSeek answer, таймаут BAAI 3 с и fallback на listwise. В 1С `ВызватьИИ` берёт модель из константы, ключ `АИС_КлючИИ` задан; при `diagnostics.rerank=true` listwise пропускается. Полный eval: found 0.95, citation accuracy 0.912, correctness 0.9375, no-answer precision 0.769, retrieval p95 1.1 с, e2e p95 10.5 с; 68/70 BAAI, 2 fallback. Остаточные 3 ложных отказа: один пункт ГОСТ не попал в контекст и два вопроса по учебнику, где в контексте только заголовки разделов.

## 2. Приоритеты

### P0. Полная переиндексация пилота и повторный eval

Статус на 2026-11-05: Cloud.ru embeddings и BAAI доступны; GigaChat-модели не использовать до явного указания. Alias переведён на Cloud.ru-коллекцию; answer-модель для новых прогонов — DeepSeek, пока не будет отдельного решения по production.

- [x] Собрать indexer с PaddleOCR (`WITH_PADDLE=1`).
- [x] Исправить системные зависимости OCR: `libgl1`, `libglib2.0-0`, `libgomp1`, `libsm6`, `libxext6`, `libxrender1` в `rag-service/Dockerfile.indexer`; OCR проверен на реальной странице.
- [x] Создать новую коллекцию через `collection-create`.
- [x] Переиндексировать 30 пилотных документов с `--ocr paddle`, `PIPELINE_VERSION=2`, `--target-collection <new>`.
- [x] Перейти на Cloud.ru Foundation Models (`ai-sage/Giga-Embeddings-instruct-480M`, 1024); reranker `BAAI/bge-reranker-v2-m3` включён с лимитом 15 и таймаутом 3 с.
- [x] Проверить, что в новой коллекции у 2 «учебниковых» кейсов есть текст разделов: полная переиндексация 30/30, 5538 чанков.
- [x] Прогнать retrieval-eval и answer-eval на новой коллекции с `group_size=5`, без parent, labels-only.
- [x] Сравнить с текущими метриками; зафиксировать результат в `docs/rag-evaluation.md`.
- [x] Rollout: production 8080 перезапущен с Cloud.ru embeddings, alias `ai_scrivener_knowledge_current` переведён на `cloudru_pilot_v1_1793908370`; retrieval eval 1.0/1.0/1.0, p95 180 мс.
- [x] BAAI включён с `rerank_candidate_limit=15`, `rerank_batch_size=15`, `rerank_timeout_seconds=3`; при таймауте/ошибке используется RRF/listwise fallback.

Критерий: found_rate ≥ 0.9667, citation_accuracy ≥ 0.95, no_answer_precision ≥ 0.90 на полной переиндексации, а не на rechunk. Текущий dev: found 0.95, citation_accuracy 0.912, no_answer_precision 0.769; 3 ложных отказа.

- [~] Полная переиндексация 170 уникальных документов запущена: коллекция `cloudru_full_v1_1793918359`, прогресс в `artifacts/rag-reindex-full`; alias не переключён.

### P1. Развернуть проверенные изменения

- [x] Пересобрать/перезапустить `rag-service` с `group_size=5`, `include_parent=false`, Cloud.ru provider.
- [x] Переключить alias на `cloudru_pilot_v1_1793908370`; retrieval eval на production: 1.0/1.0/1.0, p95 180 мс.
- [ ] Обновить активный промпт `ОтветПоБазеЗнаний` в базе 1С на формат `citations: [string]`; runtime-инструкция уже добавлена, но текст промпта в БД нужно привести к той же схеме.
- [ ] Прогнать ручной e2e-сценарий из 1С на 5–10 вопросах: found, citations, источники, ошибки.
- [ ] Зафиксировать rollback: alias обратно на старую коллекцию невозможен без GigaChat; хранить старую коллекцию только как архив.

Критерий: 1С получает ответы с валидными citations, alias переключён. Текущий dev-контур: found 0.95, citation_accuracy 0.912, correctness 0.9375, e2e p95 10.5 с; ключ `АИС_КлючИИ` задан, модель — deepseek-chat.

### P1. Латентность

- [ ] Замерить разбивку: retrieval, rerank, LLM, валидация citations, total.
- [ ] Проверить более быструю/не-reasoning модель для ответа и/или реранка.
- [ ] Проверить сокращение контекста (`group_size`, `rerank_max_candidates`, `max_tokens`).
- [ ] Оценить streaming/асинхронную выдачу для UI 1С.
- [ ] Зафиксировать реалистичный target, если p95 < 3 с недостижим на текущей модели.

Критерий: p95 e2e либо < 3 с, либо согласованный новый target. Текущий dev p95 10.5 с; основной вклад — answer-стадия.

### P2. No-answer и abstention

- [ ] После P0 проверить, исчезли ли 2 ложных отказа.
- [ ] Если false_refusals > 1 — добавить порог/классификатор релевантности для `found=false`.
- [ ] Проверить `no_answer_precision` и `no_answer_recall` на 10 no-answer кейсах.
- [ ] Не вводить `search_min_score` наугад: RRF-скоры не калиброваны; использовать rerank-score или отдельный классификатор.

Критерий: `no_answer_precision ≥ 0.90`, `no_answer_recall` не ниже 0.95.

### P2. Расширение golden set и корпуса

- [ ] Добавить кейсы на остальные 53 типа документов.
- [ ] Расширить набор до 100–150 вопросов на полном корпусе.
- [ ] Добавить вопросы с точными идентификаторами (номера ГОСТ, статьи, таблицы).
- [ ] Проверить, что expected_clauses совпадают с реальными чанками после полной переиндексации.
- [ ] Зафиксировать версию golden set и манифеста корпуса.

Критерий: покрыты все типы, метрики пересчитаны на полном корпусе.

### P2. 1С: аудит и мониторинг

- [x] Аудит Q&A: `АИС_ОтветПоБазеЗнаний` пишет запись в `АИС_ИсторияДействийИИ` (вопрос JSON, ответ LLM, модель, результат, ошибка, длительность). Требуется публикация расширения.
- [ ] Метрики `/health`, points_count, latency, доля found=false.
- [ ] Инструкция по переиндексации и rollback в `guides/runbook.md`.

## 3. Команды для повторного eval

```bash
# 1. Запустить временный RAG-сервис на проверяемой коллекции
NEW=<collection-name>
docker run -d --rm --name rag-eval-tmp --network deploy_default \
  -p 127.0.0.1:8081:8080 --env-file rag-service/.env \
  -e RAG_QDRANT_COLLECTION="$NEW" \
  -e RAG_GIGACHAT_CA_BUNDLE=/config/russian_trusted_root_ca.pem \
  -e FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
  -v deploy_fastembed_cache:/app/.cache/fastembed \
  deploy-rag-service:latest

# 2. Retrieval eval
set -a; . rag-service/.env; set +a
uv run --project rag-service python -m rag_service.eval \
  --base-url http://127.0.0.1:8081 \
  --dataset rag-service/eval/golden/knowledge.jsonl \
  --top-k 10

# 3. Answer eval
set -a; . ./.env; set +a
uv run python -m tools.llm_eval \
  --rag-url http://127.0.0.1:8081 \
  --group-size 5 --no-include-parent \
  --concurrency 8 \
  --output artifacts/llm-eval/knowledge-answer-final.json

# 4. Остановить временный сервис
docker stop rag-eval-tmp
```

## 4. Риски и ограничения

- Rechunk-коллекция не заменяет полную переиндексацию: текст взят из старых чанков, OCR не повторялся.
- `include_parent=true` вреден при текущем trim: контекст растёт в 4–5 раз, нужный пункт теряется. Не включать без переделки `_trim_to_token_budget`.
- `group_size=10` даёт полное покрытие пункта, но ухудшает found_rate/citation precision и latency; не использовать без новой проверки.
- LLM-judge не является истиной; 3 judge error в последнем прогоне исключены из метрик.
- `no_answer_accuracy` retrieval остаётся 0.0, пока нет порога отсечения; answer-метрика no-answer считается отдельно.
- Секреты (`DEEPSEEK_API_KEY`, `RAG_SERVICE_TOKEN`) не коммитить.

## 5. Definition of Done

- Полная переиндексация пилота с Paddle/OCR выполнена, alias переключён после ручного e2e.
- `citation_accuracy ≥ 0.95`, `no_answer_precision ≥ 0.90`, `found_rate ≥ 0.95`, `correctness` не ниже 0.90.
- p95 e2e < 3 с или согласованный новый target.
- Golden set покрывает все 68 типов; метрики пересчитаны на полном корпусе.
- Аудит Q&A в 1С и runbook обновлены.
