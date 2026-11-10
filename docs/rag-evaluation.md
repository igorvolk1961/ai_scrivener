# Метрики и оценка RAG

Дата: 2026-11-05
Статус: рабочая техническая записка. Retrieval-метрики и answer-контур реализованы в `rag_service.eval` и `tools/llm_eval`; answer-метрики измерены как pre-chunking baseline.

Связанные документы:

- `rag-service/src/rag_service/eval.py` — текущий harness;
- `rag-service/eval/golden/knowledge.jsonl` — golden set v0;
- `rag-service/eval/README.md` — формат датасета и запуск;
- `plans/2026-11-04-effective-rag.md` §1.1, §7 — целевые метрики и этапы;
- `plans/implementation_plan.md` §11 — метрики приёмки.

## 1. Что оценивается

Контур Q&A разделён на два независимых слоя:

1. **Retrieval** — что вернул `/v1/retrieve`: правильный документ и пункт попали в top-k или нет.
2. **Answer** — что сгенерировала LLM по найденному контексту: ответ правильный, citations валидны, утверждения подтверждены источниками.

Разделение важно: плохой ответ при хорошем retrieval — это ошибка генерации или промпта; плохой retrieval при хорошем ответе — случайное попадание или параметрическая память модели, которое нельзя считать подтверждённым знанием.

## 2. Обозначения

Для одного кейса:

- `Q` — вопрос;
- `k` — `top_k`, по умолчанию 10;
- `R = [r1, ..., rk]` — результаты `/v1/retrieve` после группировки по источнику;
- `S = {s1, ..., sm}` — ожидаемые `source_id` из golden set;
- `C = {c1, ..., cn}` — ожидаемые номера пунктов из golden set;
- `found` — найден ли ожидаемый источник или пункт в `R`.

Текущий harness считает метрики по кейсам (macro-average): каждый вопрос даёт одно значение, итог — среднее по вопросам. Это не micro-average по чанкам, поэтому один документ с сотней чанков не перевешивает остальные вопросы.

## 3. Retrieval-метрики

### 3.1. Recall@k (в текущей реализации — hit rate)

В `rag_service.eval` для кейса:

```text
recall = 1, если ожидаемый source_id или clause найден в top-k
recall = 0, иначе
Recall@k = среднее recall по answerable-кейсам
```

Код: `run_eval` (`rag-service/src/rag_service/eval.py:144`), `_find_rank` (`:176`).

Важно: это **per-case hit rate**, а не set recall. Если в кейсе несколько ожидаемых источников, код всё равно возвращает 1 при первом совпадении. В golden set v0 у каждого кейса один ожидаемый `source_id` и не более одного `clause`, поэтому текущая метрика совпадает с обычным Recall@k. Для кейсов с несколькими ожидаемыми источниками нужна отдельная set-aware реализация:

```text
Recall@k = |найденные ожидаемые источники| / |S|
```

Пример: ожидаемый пункт `4.2.5` найден на позиции 7 при `k = 10` → `recall = 1`. На позиции 11 → `recall = 0`.

### 3.2. MRR@k

Mean Reciprocal Rank — насколько высоко стоит первый правильный результат:

```text
MRR(q) = 1 / rank, если правильный результат найден
MRR(q) = 0, иначе
MRR@k = среднее MRR(q) по answerable-кейсам
```

`rank` — позиция первого результата, у которого совпал `source_id` или `clause` (нумерация с 1). Код: `run_eval` (`:144`).

Примеры:

| Позиция первого попадания | MRR(q) |
|---:|---:|
| 1 | 1.000 |
| 2 | 0.500 |
| 3 | 0.333 |
| 7 | 0.143 |
| не найдено | 0.000 |

MRR не различает позиции 8, 9 и 10 — все дают небольшой вклад. Поэтому его смотрят вместе с nDCG и Recall.

### 3.3. nDCG@k

Normalized Discounted Cumulative Gain в текущей реализации — бинарная релевантность одного попадания:

```text
DCG(q) = 1 / log2(rank + 1), если попадание есть
DCG(q) = 0, иначе

R = len(expected_source_ids), если список не пуст,
    иначе len(expected_clauses), иначе 1

IDCG(q) = сумма по i = 1..min(R, k) от 1 / log2(i + 1)

nDCG(q) = DCG(q) / IDCG(q)
nDCG@k = среднее nDCG(q) по answerable-кейсам
```

Код: `_ndcg` (`:194`), `_log2` (`:226`).

Пример для одного ожидаемого источника (`R = 1`):

| Позиция | DCG | IDCG | nDCG |
|---:|---:|---:|---:|
| 1 | 1.000 | 1.000 | 1.000 |
| 2 | 0.631 | 1.000 | 0.631 |
| 3 | 0.500 | 1.000 | 0.500 |
| 10 | 0.289 | 1.000 | 0.289 |

Ограничение: при `R > 1` фактический DCG учитывает только первое попадание, а IDCG — все `R` ожидаемых. Поэтому даже при идеальном наборе найденных документов nDCG будет меньше 1. Это осознанное упрощение v0; для полноценного nDCG нужна бинарная релевантность каждого результата и сумма по всем найденным релевантным позициям:

```text
DCG@k   = Σ rel_i / log2(i + 1), i = 1..k
IDCG@k  = Σ 1 / log2(i + 1),    i = 1..min(|S|, k)
nDCG@k  = DCG@k / IDCG@k
```

Если в кейсе заданы и `expected_source_ids`, и `expected_clauses`, текущий код берёт `R` по числу источников, а не по сумме источников и пунктов. В golden set v0 это не проявляется, потому что на кейс один источник.

### 3.4. No-answer accuracy

Для кейсов с `"no_answer": true`:

```text
no_answer_ok = 1, если /v1/retrieve вернул пустой список results
no_answer_ok = 0, иначе
no_answer_accuracy = среднее no_answer_ok
```

Код: `run_eval` (`:144`) и `_metrics` (`:209`). Проверяется именно пустой список после `top_k`; ожидаемые `source_id`/`clause` для таких кейсов не задаются.

Текущий результат `0.000` — не ошибка расчёта, а свойство конфигурации: `search_min_score: 0.0`, поэтому dense/hybrid поиск всегда возвращает top-k. Чтобы метрика стала осмысленной, нужен порог отсечения (отдельная задача плана: «Нет порога» в §4).

### 3.5. Latency p50/p95

Замеряется время одного вызова `/v1/retrieve`:

```text
latency(q) = время от начала HTTP-запроса до получения ответа
```

Код: `run_eval` (`:144`) и `_percentile` (`:231`). В замер входит сеть до сервиса и работа retrieval внутри сервиса, но не генерация ответа LLM.

Перцентиль считается по сортированному массиву:

```text
index = round(p / 100 * (n - 1))
percentile = sorted(values)[index]
```

Для 70 кейсов p95 — это `round(0.95 * 69) = 66`, то есть 67-е значение в отсортированном массиве (индексация с 0). p50 — медиана.

Особенности:

- нет прогрева: первый запрос может быть медленнее из-за инициализации моделей;
- нет разделения на cold/warm;
- p95 на 70 кейсах статистически шумный: одно выбросное значение сдвигает метрику;
- для e2e-метрики Q&A нужен отдельный замер retrieve + LLM + валидация citations.

### 3.6. Служебные счётчики

В отчёт также попадают:

- `cases` — общее число кейсов;
- `answerable_cases` — число кейсов с непустыми `expected_source_ids` или `expected_clauses`.

Это знаменатели метрик. Если `answerable_cases = 0`, текущий код возвращает `0.0` для Recall/MRR/nDCG, а не `NaN`; при интерпретации отчёта это нужно проверять.

## 4. Как определяется попадание

`_find_rank` (`rag-service/src/rag_service/eval.py:176`) перебирает результаты в порядке выдачи и возвращает позицию первого совпадения:

```text
совпадение = result.source_id ∈ S
             или (result.chunks[*].clause ∩ C ≠ ∅)
```

Следствия:

1. **Совпадение по пункту не привязано к ожидаемому источнику.** Если другой документ содержит пункт с тем же номером, он тоже даст попадание. Для пунктов `1.1`, `2.1` это реальный риск; в golden set v0 используются более специфичные пункты и фильтр `doc_types`, но полностью риск не устранён. Строгая проверка должна требовать пару `(source_id, clause)`.
2. **Ранжирование — по документам, а не по чанкам.** При `group_by_source: true` один результат — это документ с несколькими чанками; `rank` — позиция документа. Внутри документа порядок чанков не влияет на позицию.
3. **`top_k` обрезает выдачу до проверки.** Если правильный документ на позиции 11, при `k = 10` он считается ненайденным, даже если физически был в candidate_k.
4. **Фильтры передаются в `/v1/retrieve` как есть.** Неверный `doc_types` даёт пустую выдачу и обнуляет answerable-метрики, а не просто понижает их. В golden set v0 фильтр соответствует типу документа; прогон без фильтров дал те же метрики.

`expected_pages`, `doc_type`, `answer_type`, `difficulty` и `notes` текущий retrieval-harness не использует: они хранятся для answer-проверок и ручного ревью. `filters` при этом применяются на стороне `/v1/retrieve`, поэтому ошибка в фильтре меняет саму выдачу, а не только проверку.

Для answer-метрик нужна более строгая функция сопоставления:

```text
match(citation, golden) = citation.source_id == golden.source_id
                          и (golden.clause пуст или citation.clause == golden.clause)
```

## 5. Answer-метрики

Эти метрики требуют вызова LLM и реализованы в `tools/llm_eval`, который использует тот же промпт `ОтветПоБазеЗнаний` и ту же модель, что production-контур в 1С.

### 5.1. Citation validity (precision цитат)

Для ответа с `found = true`:

```text
C_valid = цитаты, у которых source_id есть в выданном контексте,
          а clause (если указан) существует в чанках этого источника

citation_precision = |C_valid| / |C_all|
```

Если `C_all` пуст при `found = true`, это нарушение контракта: ответ без citations не считается валидным. Для пустого знаменателя метрика должна быть `0` (или отдельный счётчик `answers_without_citations`), а не `NaN`.

Дополнительно считается `citation_validity_rate`:

```text
доля ответов с found = true, у которых все citations валидны
```

### 5.2. Citation recall / coverage

Покрытие ожидаемых источников и пунктов:

```text
E = ожидаемые пары (source_id, clause) из golden set
C = пары, указанные в citations ответа

citation_recall = |E ∩ C| / |E|
```

Если `expected_clauses` пуст, сравниваются только `source_id`. Метрика отвечает на вопрос «сослался ли ответ на тот документ/пункт, который мы считали правильным», а не «нет ли лишних цитат».

### 5.3. Citation accuracy (строгая, для приёмки)

Целевой порог плана — ≥ 0,95 для `found = true`. Предлагаемое строгое определение:

```text
citation_accuracy =
    доля кейсов с found = true, для которых одновременно:
      1) citations непусты;
      2) все citations валидны;
      3) хотя бы одна citation покрывает ожидаемый source_id/clause
```

Это не среднее по цитатам, а доля корректных ответов. Она штрафует и пропуск цитаты, и лишнюю невалидную цитату. Дополнительно полезно хранить раздельно `citation_precision` и `citation_recall`, чтобы видеть причину падения.

### 5.4. Answer correctness

Есть два режима.

**Reference-based (дешевле и стабильнее).** В golden set хранится эталонный ответ или набор ключевых фактов `K`:

```text
correctness = |K ∩ факты в ответе| / |K|
```

Для бинарной приёмки: `correct = 1`, если все ключевые факты присутствуют и нет противоречащих утверждений.

**LLM-judge (для свободных формулировок).** Судье передаются вопрос, эталон, ответ и рубрика:

```text
2 — ответ полный и точный;
1 — частично верный или неполный;
0 — неверный, противоречащий или «не найдено» при наличии ответа.
correctness = score / 2
```

Требования к судье:

- temperature 0, фиксированный seed, версия промпта;
- отдельная модель или отдельный вызов, не тот же ответ, который оценивается;
- кэш вердиктов по хешу `(вопрос, ответ, контекст, версия промпта, модель)`;
- ручная проверка 10–20% вердиктов на калибровку;
- для русского языка рубрика и эталон тоже на русском.

LLM-judge не является истиной: его надо валидировать на размеченной подвыборке и фиксировать agreement с человеком.

### 5.5. Groundedness / faithfulness

Проверяет, что ответ не добавил knowledge «от себя». Разбиваем ответ на атомарные утверждения (claims), для каждого ищем подтверждение **только в цитируемых фрагментах**, а не во всём контексте:

```text
grounded(claim) = 1, если хотя бы одна цитата подтверждает claim
groundedness = Σ grounded(claim) / |claims|
strict_groundedness = 1, если все claims подтверждены, иначе 0
```

Реализация: NLI-модель (entailment) или LLM-judge с вопросом «следует ли утверждение из данного фрагмента?». Важно:

- проверять только цитируемые фрагменты, иначе метрика измеряет не то;
- отличать `groundedness` от `correctness`: правильный, но неподтверждённый ответ — это утечка параметрической памяти, а не знание из корпуса;
- числовые утверждения проверять отдельно: LLM-судья часто пропускает подмену единиц и диапазонов.

### 5.6. No-answer precision и recall

Для answer-контура нужна матрица ошибок по признаку «ответа нет»:

| | golden: ответа нет | golden: ответ есть |
|---|---|---|
| система: `found = false` | TP | FP (ложный отказ) |
| система: `found = true` | FN (галлюцинация) | TN |

```text
no_answer_precision = TP / (TP + FP)
no_answer_recall    = TP / (TP + FN)
```

Это не то же самое, что retrieval `no_answer_accuracy`: retrieval-метрика проверяет пустую выдачу, answer-метрика — итоговое поведение LLM. В плане указан порог no-answer precision ≥ 0,90.

### 5.7. End-to-end latency

Для Q&A:

```text
e2e_latency = retrieve + LLM + validation + UI-подготовка
```

Считаются p50, p95 и, при необходимости, p99. Полезно хранить разбивку:

- `retrieval_ms` — из `diagnostics.retrieval_ms`;
- `rerank_ms` — если включён;
- `llm_ms` — вызов DeepSeek;
- `validation_ms` — проверка citations;
- `total_ms`.

Порог плана — p95 `/v1/retrieve` + LLM < 3 с.

### 5.8. Реализация

`tools/llm_eval` повторяет production-цепочку: `/v1/retrieve` → listwise-реранк теми же кандидатами и промптом → контекст `[S1]…[Sn]` → ответ DeepSeek → детерминированная валидация citations → LLM-judge для correctness и groundedness.

Особенности реализации:

- кэш ответов по ключу `(модель, system, user, temperature, max_tokens)` в `artifacts/llm-eval/cache`;
- при невалидном citation ответ переводится в `found = false`, как в `АИС_ОтветПоБазеЗнаний`;
- при недоступности реранка используется порядок RRF, fallback считается отдельно;
- judge вызывается только для `found = true`; при ошибке разбора его вердикт не подменяется нулём;
- ошибки retrieval/answer исключаются из answer-метрик и видны отдельно;
- в отчёт пишутся `expected_clause_in_context`, `raw_citations` и `rerank_error` для диагностики;
- результат сохраняется в JSON и Markdown.

## 6. Агрегация и отчётность

Правила, которые важно соблюдать:

1. **Макро-усреднение по кейсам.** Каждый вопрос имеет равный вес. Нельзя усреднять метрики по чанкам или по документам.
2. **Разные знаменатели.** Recall/MRR/nDCG считаются только по answerable-кейсам; no-answer — только по no-answer-кейсам; citation-метрики — только по `found = true`. В отчёте должны быть видны числитель и знаменатель.
3. **Не подменять пустой знаменатель нулём.** Текущий код возвращает `0.0` для пустых списков; для приёмки лучше выводить `null` и `cases_without_denominator`.
4. **Доверительные интервалы.** На 60 answerable-кейсах 95%-й интервал для Recall@10 вблизи значений 0,9–1,0 имеет ширину примерно ±6–8 п.п.; разница 0,95 и 1,00 на такой выборке статистически незначима. Для пропорций использовать Wilson interval, для MRR/nDCG — bootstrap по кейсам.
5. **Фиксировать версию.** В отчёт писать: датасет, его хеш, коллекция Qdrant, alias, версия промпта, модель LLM, `chunker_version`, конфигурация retrieval.
6. **Разделять retrieval и answer.** Нельзя делать вывод «RAG стал лучше» по e2e-метрике, если изменение касалось только промпта.

Рекомендуемая структура JSON-отчёта:

```json
{
  "run": {
    "dataset": "rag-service/eval/golden/knowledge.jsonl",
    "dataset_sha256": "...",
    "collection": "ai_scrivener_knowledge_pilot_1793864097",
    "top_k": 10,
    "model": "deepseek-chat",
    "prompt_version": "..."
  },
  "retrieval": {
    "cases": 60,
    "recall_at_k": 1.0,
    "mrr_at_k": 0.9833,
    "ndcg_at_k": 0.9877,
    "no_answer_accuracy": 0.0,
    "latency_p50_ms": 138.06,
    "latency_p95_ms": 266.97
  },
  "answer": {
    "citation_precision": null,
    "citation_recall": null,
    "citation_accuracy": null,
    "correctness": null,
    "groundedness": null,
    "no_answer_precision": null,
    "e2e_latency_p95_ms": null
  }
}
```

## 7. Текущий baseline

Golden set v0: 70 кейсов, 60 answerable, 10 no-answer, 15 типов, 30 документов пилотной коллекции.

### 7.1. Retrieval

```text
Recall@10          = 1.000
MRR@10             = 0.9917
nDCG@10            = 0.9938
no-answer accuracy = 0.000
latency p50        = 160–185 мс
latency p95        = 295–3928 мс
```

Разброс p95 между прогонами объясняется холодным стартом embedding/модели. Прогон без `filters.doc_types` дал те же значения: запросы сами по себе различают документы. Это baseline только для 30 проиндексированных документов; после полной индексации его нужно переснять.

Запуск:

```bash
set -a; . rag-service/.env; set +a
uv run --project rag-service python -m rag_service.eval \
  --dataset rag-service/eval/golden/knowledge.jsonl \
  --top-k 10 \
  --output artifacts/rag-eval/knowledge-baseline.json
```

### 7.2. Answer (pre-chunking baseline)

```text
found_rate                     = 0.4167
false_refusal_rate             = 0.5833
expected_clause_in_context     = 0.8000
false_refusals_with_context    = 23 из 35
citation_precision             = 0.3553
citation_recall                = 0.4167
citation_accuracy              = 0.8000
correctness                    = 0.3661  (56 кейсов)
groundedness                   = 0.9843  (21 кейс)
no_answer_precision            = 0.2222
no_answer_recall               = 1.0000
rerank_fallbacks               = 22 из 70
judge_errors                   = 4
```

Интерпретация:

- документ находится почти всегда (Recall@10 = 1.0), но **ожидаемый пункт попал в контекст только в 80%** answerable-кейсов;
- из 35 ложных отказов 23 случились при наличии нужного пункта в контексте — это ошибки citations/промпта, а 12 — следствие чанкинга/`group_size`;
- `citation_precision` низкая потому, что модель часто указывает `source_id` с пунктом, которого нет в конкретном чанке; production-валидация такие citations отбрасывает;
- `groundedness` высокая только на 21 ответе, где удалось получить вердикт judge; это выборка смещена в сторону удачных ответов;
- 22 из 70 кейсов ушли в rerank-fallback: listwise-реранк на `deepseek-v4-flash` нестабильно отдаёт JSON;
- `no_answer` retrieval = 0, потому что порог отсечения не задан; answer-контур отказался от ответа на всех 10 no-answer кейсах, но precision 0.22 из-за 35 ложных отказов на answerable.

Это **не приёмочные метрики**: они измерены до исправления чанкинга и при нестабильном реранке. Использовать их можно как baseline «до», а не как оценку модели или промпта. После этого прогона чанкер исправлен (`PIPELINE_VERSION=2`): пункт больше не теряется при слиянии соседних чанков, номера заголовков наследуются, list items не считаются пунктами. Переиндексация и повторный прогон ещё не выполнены.

E2E-латентность без кэша: p50 ≈ 11.4 с, p95 ≈ 34.3 с. В прогоне с кэшем p50 падает до ~0.18 с, потому что ответы и judge берутся из локального кэша; такие значения не отражают production.

Запуск answer-контура:

```bash
set -a; . ./.env; set +a
uv run python -m tools.llm_eval \
  --dataset rag-service/eval/golden/knowledge.jsonl \
  --concurrency 8 \
  --output artifacts/llm-eval/knowledge-answer-eval.json
```

`tools.llm_eval` читает `DEEPSEEK_*` из `.env` и `RAG_SERVICE_TOKEN` из `rag-service/.env`. Для чистого замера латентности нужен `--no-cache`, для быстрой итерации — кэш.

### 7.3. После rechunk пилота

Чтобы проверить эффект чанкера без повторного OCR, старые чанки пилота были пересобраны в документы и перечанкованы; табличные чанки сохранены как есть. Новая коллекция: `ai_scrivener_knowledge_pilot_v2b_1793897131`, alias не переключался.

| Метрика | До исправления | После rechunk |
|---|---:|---:|
| Recall@10 | 1.0000 | 1.0000 |
| MRR@10 | 0.9917 | 1.0000 |
| nDCG@10 | 0.9938 | 1.0000 |
| found_rate | 0.4167 | 0.5000 |
| expected_clause_in_context | 0.8000 | 0.8167 |
| citation_precision | 0.3553 | 0.4568 |
| citation_accuracy | 0.8000 | 0.8000 |
| correctness | 0.3661 | 0.4655 |
| groundedness | 0.9843 | 0.9654 |
| false_refusals | 35 | 30 |
| false_refusals_with_context | 23 | 19 |
| rerank_fallbacks | 22 | 24 |
| no_answer_precision | 0.2222 | 0.2500 |
| no_answer_recall | 1.0000 | 1.0000 |

Выводы:

- Исправление чанкера подтверждено: retrieval-метрики выросли до идеальных, `found_rate` и correctness заметно улучшились.
- 30 ложных отказов остаются; 19 из них — при наличии нужного пункта в контексте. Это уже не чанкинг, а citations/промпт/реранк.
- `rerank_fallbacks` не уменьшился (24 из 70): listwise-реранк остаётся отдельным дефектом.
- `no_answer_precision` низкая из-за ложных отказов, а не из-за галлюцинаций: `hallucinated_answers = 0`, `no_answer_recall = 1.0`.
- Rechunk не заменяет полную переиндексацию: текст взят из старых чанков, OCR и извлечение не повторялись. Для production нужна переиндексация корпуса с Paddle/OCR и проверка на полном наборе.

Следующие шаги по answer-качеству: контракт citations в промпте, затем латентность и порог abstention для no-answer.

#### Rerank stability experiment

Отдельный rerank-only прогон на тех же 70 кейсах:

| Режим | Fallback | Empty ranking | p50 | p95 |
|---|---:|---:|---:|---:|
| 30 кандидатов, без JSON mode | 24 | 11 | — | — |
| 30 кандидатов, JSON mode | 0 | 12 | 4460 мс | 24795 мс |
| 15 кандидатов, JSON mode | 0 | 14 | 4123 мс | 9881 мс |

Вывод: JSON mode убирает технические fallback-и полностью. Оставшиеся `empty ranking` — это валидный ответ модели «ни один кандидат не релевантен», а не сбой парсинга; код в этом случае сохраняет порядок RRF. Ограничение до 15 кандидатов снижает p95 примерно с 24,8 до 9,9 с. В production-контуре 1С включены JSON mode и первые 15 кандидатов; eval по умолчанию повторяет эти настройки. Это ещё не полный answer-eval: метрики качества нужно переснять после полной переиндексации.

Полный answer-eval после стабилизации реранка (та же rechunk-коллекция, 70 кейсов):

```text
found_rate                 = 0.5000
false_refusal_rate         = 0.5000
expected_clause_in_context = 0.8167
false_refusals_with_context = 19
citation_precision         = 0.3977
citation_recall            = 0.5000
citation_accuracy          = 0.8667
correctness                = 0.4831
groundedness               = 0.9655
rerank_fallbacks           = 0
rerank_empty_rankings      = 12
no_answer_precision        = 0.2500
no_answer_recall           = 1.0000
e2e p50 / p95              = 8.3 с / 18.3 с
```

По сравнению с прогоном до стабилизации реранка: correctness 0.4655 → 0.4831, citation accuracy 0.8000 → 0.8667, e2e p95 48.3 → 18.3 с; citation precision немного снизилась (0.4568 → 0.3977), потому что модель стала чаще возвращать citations, часть которых всё ещё не проходит валидацию. Ложные отказы не изменились (30), из них 19 — при наличии пункта в контексте. Главный оставшийся дефект — контракт citations, затем `group_size`/`include_parent`.

#### Context experiment: `group_size` и `include_parent`

Замер только retrieval+контекста, без LLM, на 60 answerable-кейсах:

| Режим | Expected clause in context | Средне чанков | Средне символов | p50 | p95 |
|---|---:|---:|---:|---:|---:|
| `group_size=3`, без parent (текущий дефолт до правки) | 0.9500 | 7.2 | 6 327 | 111 мс | 7 707 мс |
| `group_size=5`, без parent | 0.9667 | 11.0 | 9 429 | 111 мс | 7 220 мс |
| `group_size=10`, без parent | 1.0000 | 19.0 | 15 444 | 115 мс | 7 664 мс |
| `group_size=3`, с parent | 0.8167 | 48.1 | 36 022 | 200 мс | 3 636 мс |
| `group_size=5`, с parent | 0.8000 | 53.8 | 39 193 | 276 мс | 7 215 мс |
| `group_size=10`, с parent | 0.8167 | 59.0 | 42 095 | 331 мс | 8 602 мс |

Выводы:

- `include_parent=true` не помогает: он раздувает контекст в 4–5 раз, но снижает `expected_clause_in_context` до 0.80–0.82, потому что при добавлении parent-чанков и trim по бюджету теряется исходный пункт. В `config/parameters.yaml` выставлено `include_parent: false`.
- `group_size=5` даёт 0.9667 при 9,4 тыс. символов; `group_size=10` даёт 1.0, но 15,4 тыс. символов. Для пилота выбран `group_size=5`.
- p95 retrieval в этом эксперименте шумный из-за холодного старта; важнее рост среднего числа чанков и символов.

#### Answer eval после context fix (`group_size=5`, без parent)

```text
found_rate                 = 0.6167
false_refusal_rate         = 0.3833
expected_clause_in_context = 0.9667
false_refusals_with_context = 22
citation_precision         = 0.4713
citation_recall            = 0.5833
citation_accuracy          = 0.8649
correctness                = 0.5818
groundedness               = 0.9891
rerank_fallbacks           = 0
rerank_empty_rankings      = 5
no_answer_precision        = 0.3030
no_answer_recall           = 1.0000
e2e p50 / p95              = 7.0 с / 98.4 с
```

Эффект:

- ложные отказы 30 → 23; отказы из-за отсутствия пункта в контексте 11 → 1 (23 всего, 22 — при наличии пункта);
- found_rate 0.50 → 0.6167, correctness 0.483 → 0.5818;
- citation precision 0.398 → 0.471, recall 0.50 → 0.583;
- теперь почти все ложные отказы (22 из 23) — это снова отбраковка citations, а не контекст. Следующий приоритет — контракт citations.
- e2e p95 98 с — выброс из-за одного долгого LLM/judge-вызова; p50 7.0 с. Латентность всё ещё выше цели 3 с и требует отдельного трека.


#### Citation contract: только метки `[S1]`

Модель больше не указывает `source_id` и `clause` вручную: в `citations` возвращается массив меток, например `["S1", "S2"]`. Сервер сопоставляет метку с кандидатом и подставляет реальные `source_id`/`clause`. Старый формат объектов сохранён для обратной совместимости.

Результаты полного eval на той же rechunk-коллекции:

| Метрика | `group_size=5` | `group_size=10` |
|---|---:|---:|
| found_rate | **0.9667** | 0.9500 |
| false_refusals | **2** | 3 |
| expected_clause_in_context | 0.9667 | 1.0000 |
| citation_precision | **0.9759** | 0.8750 |
| citation_recall | 0.9333 | 0.9333 |
| citation_accuracy | 0.9655 | **0.9825** |
| correctness | **0.9386** | 0.9298 |
| groundedness | 0.9982 | 1.0000 |
| no_answer_precision | **0.8333** | 0.7692 |
| no_answer_recall | 1.0000 | 1.0000 |
| rerank_fallbacks | 0 | 0 |
| e2e p50 / p95 | **5.7 / 10.9 с** | 7.6 / 43.0 с |

Выводы:

- Контракт меток убрал основную причину ложных отказов: 23 → 2, citation precision 0.47 → 0.976, correctness 0.582 → 0.939.
- `group_size=10` даёт полное покрытие пункта, но добавляет шум: found_rate и correctness падают, citation precision 0.875, p95 43 с. Оставляем `group_size=5`.
- Остались 2 ложных отказа (оба — отсутствие пункта в контексте на `group_size=5`), `no_answer_precision=0.833` и латентность p95 ≈ 11 с.
- Следующие шаги: latency-трек, abstention/no-answer, полная переиндексация и расширение golden set.


### 7.4. Cloud.ru embeddings и reranker

GigaChat embeddings вернул `402 Payment Required`; для разблокировки подключён Cloud.ru Foundation Models:

- embeddings: `ai-sage/Giga-Embeddings-instruct-480M`, размерность 1024;
- reranker: `BAAI/bge-reranker-v2-m3` через `/score`;
- полная переиндексация 30 пилотных документов с PaddleOCR: 30/30, 5538 чанков, коллекция `cloudru_pilot_v1_1793908370`.

Результаты полного answer-eval на Cloud.ru-коллекции (`group_size=5`, без parent, labels-only):

| Метрика | Без RAG-rerank | С Cloud.ru cross-encoder (50) + DeepSeek listwise + answer |
|---|---:|---:|
| Recall@10 / MRR / nDCG | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| found_rate | 0.9333 | **0.9500** |
| false_refusals | 4 | **3** |
| expected_clause_in_context | 0.8833 | **0.9333** |
| citation_precision | 0.8111 | **0.8710** |
| citation_recall | 0.8333 | **0.8833** |
| citation_accuracy | 0.8929 | **0.9298** |
| correctness | 0.9123 | **0.9298** |
| groundedness | 1.0000 | 1.0000 |
| no_answer_precision | 0.7143 | **0.7692** |
| no_answer_recall | 1.0000 | 1.0000 |
| retrieval p95 | 0.76 с | 17.0 с |
| e2e p50 / p95 | 6.2 / 13.1 с | 8.3 / 39.1 с |

Выводы:

- Cloud.ru полностью разблокировал индексацию и retrieval; качество немного ниже, чем у v2b на GigaChat, но сервис снова работоспособен.
- Cloud.ru reranker улучшает found/citation/correctness, но p95 retrieval 17 с и e2e 39 с — для production в таком виде не подходит. Нужно ограничить число кандидатов на реранк и/или батчи, прежде чем включать.
- Без RAG-reranker качество ниже цели `citation_accuracy ≥ 0.95`, но лучше, чем недоступный сервис.
- Рекомендуется временно развернуть Cloud.ru embeddings без RAG-reranker для восстановления Q&A, сохранив v2b/GigaChat для сравнения и rollback; reranker включать после тюнинга.


Production-переключение выполнено: `rag-service` перезапущен с Cloud.ru embeddings (1024), alias `ai_scrivener_knowledge_current` переведён на `cloudru_pilot_v1_1793908370`. Retrieval на production: Recall@10/MRR/nDCG = 1.0, p95 ≈ 180 мс. Старая GigaChat-конфигурация выведена из эксплуатации: сервер изменил политику, возврат к ней не планируется. Answer-качество production сейчас соответствует колонке «без RAG-rerank»: found_rate 0.933, citation_accuracy 0.893, correctness 0.912, e2e p95 13.1 с.


#### Корректное сравнение реранкеров: 15 против 15

Первое сравнение было некорректным: Cloud.ru cross-encoder обрабатывал 50 кандидатов (4 батча `/score`), а DeepSeek listwise — только первые 15. Добавлен параметр `rag.rerank_candidate_limit=15`: cross-encoder теперь оценивает первые 15 кандидатов, остальные сохраняются в порядке RRF, как в 1С.

| Метрика | DeepSeek listwise (15) + DeepSeek answer | Cloud.ru cross-encoder (15) + DeepSeek listwise (15) + DeepSeek answer |
|---|---:|---:|
| found_rate | 0.9333 | 0.9492 |
| citation_accuracy | 0.8929 | 0.9107 |
| correctness | 0.9123 | 0.9322 |
| no_answer_precision | 0.7143 | 0.7692 |
| retrieval p95 | 0.76 с | 1.38 с |
| e2e p50 / p95 | 6.2 / 13.1 с | 7.1 / 23.9 с |

Важно: DeepSeek в обеих колонках делает **два отдельных вызова** — сначала listwise-реранк, затем ответ. Cloud.ru cross-encoder не формирует ответ; он только переставляет кандидатов перед DeepSeek listwise. То есть в первой колонке два вызова, во второй — три (Cloud.ru `/score` + два вызова DeepSeek).

Вывод: при одинаковом числе кандидатов Cloud.ru cross-encoder даёт около +2 п.п. к found/citation accuracy и correctness, но e2e p50 растёт примерно на 0.9 с, а p95 — заметно выше. Для production это всё ещё плохой размен; DeepSeek listwise остаётся реранкером по умолчанию, cross-encoder — экспериментальный. Предыдущие 17 с retrieval и 39 с e2e относились к режиму 50 кандидатов и не должны использоваться для сравнения.


#### Постадийный бенчмарк: почему e2e растёт сильнее retrieval

20 кейсов, последовательно, без кэша и без judge, одинаковые промпты и модель ответа:

Пайплайны:

```text
A: retrieval → DeepSeek listwise → DeepSeek answer
B: retrieval → Cloud.ru cross-encoder → DeepSeek listwise → DeepSeek answer
```

**Важно:** вариант B — это двойное реранжирование. Он был собран для проверки «что даст добавление cross-encoder к уже работающему listwise», а не как кандидат в production. В production нужен **один** реранкер: либо DeepSeek listwise, либо Cloud.ru cross-encoder. Сравнение single-reranker pipeline — отдельный эксперимент.

DeepSeek listwise присутствует **в обоих** пайплайнах; в B он получает уже переставленный Cloud.ru список, поэтому его вход и latency отличаются.

| Этап | A: DeepSeek only, p50 / p95 | B: Cloud.ru 15 + DeepSeek, p50 / p95 |
|---|---:|---:|
| RAG retrieval (в B включает Cloud.ru `/score`) | 317 / 496 мс | 700 / 983 мс |
| — в том числе Cloud.ru cross-encoder | — | ≈ 383 / 487 мс (разница retrieval) |
| DeepSeek listwise (есть в обоих) | 4 368 / 6 703 мс | 5 031 / 8 108 мс |
| DeepSeek answer (есть в обоих) | 2 295 / 5 563 мс | 2 286 / 3 919 мс |
| e2e (сумма этапов) | 6 880 / 12 464 мс | 8 957 / 14 107 мс |
| контекст, символов (p50) | 13 523 | 13 214 |

Что видно:

- Стадия **answer** присутствует в обоих пайплайнах и практически не изменилась: p50 2.295 с против 2.286 с; разница в p95 — шум и разная длина ответа, а не влияние реранкера.
- **DeepSeek listwise тоже есть в обоих** пайплайнах. В B он идёт после Cloud.ru cross-encoder и получает другой порядок/состав первых 15 кандидатов, поэтому его latency отличается (+0.66 с p50). Это не «реранкер участвует в формировании ответа».
- Прирост e2e даёт дополнительный **Cloud.ru `/score`** в retrieval (+≈0.38 с p50) и изменение входа **DeepSeek listwise** (+0.66 с p50).
- p95 на 20–70 кейсах нестабилен; один долгий LLM-вызов сдвигает его сильнее, чем средний вклад cross-encoder.

Поэтому объяснение простое: answer-стадия одинаковая, а разница e2e — это дополнительный retrieval-вызов плюс изменение входа для listwise-реранка. Вывод по production не меняется: DeepSeek listwise, Cloud.ru cross-encoder — экспериментальный.


#### Итоговое paired-сравнение на 70 кейсах

Один и тот же golden set, одна коллекция, одна модель ответа и judge. Различается только реранкер:

- **A**: retrieval → DeepSeek listwise (15) → DeepSeek answer;
- **B**: retrieval → Cloud.ru cross-encoder (15) → DeepSeek answer (без listwise).

| Метрика | A: DeepSeek listwise | B: Cloud.ru cross-encoder only |
|---|---:|---:|
| found_rate | 0.9333 | **0.9500** |
| false_refusals | 4 | **3** |
| expected_clause_in_context | 0.8833 | **0.9167** |
| citation_precision | 0.8111 | **0.8602** |
| citation_recall | 0.8333 | **0.8667** |
| citation_accuracy | 0.8929 | **0.9123** |
| correctness | 0.9123 | **0.9474** |
| groundedness | 1.0000 | 1.0000 |
| no_answer_precision | 0.7143 | **0.7692** |
| no_answer_recall | 1.0000 | 1.0000 |
| retrieval p50 / p95 | **0.16 / 0.76 с** | 0.70 / 16.69 с |
| e2e p50 / p95 | 6.20 / **13.13 с** | **2.91** / 52.34 с |

Выводы:

- B немного лучше по качеству: +1.7 п.п. found, +1.9 п.п. citation accuracy, +3.5 п.п. correctness.
- B существенно лучше по p50 (2.9 с против 6.2 с), но катастрофически хуже по p95: 52 с против 13 с. Причина — хвост Cloud.ru `/score`: retrieval p95 16.7 с.
- Обе конфигурации не достигают citation_accuracy ≥ 0.95; вопрос качества ещё открыт.
- Production остаётся на A: стабильный p95 важнее p50. Cloud.ru cross-encoder-only можно пробовать только с таймаутом/fallback на RRF, чтобы срезать хвост; иначе переключать нельзя.


Важная поправка: **e2e p95 нельзя использовать как метрику реранкера**. E2E включает answer-стадию и её выбросы; 52 с — это системная latency, а не вклад `/score`. Для выбора реранкера корректны:

- latency самого этапа: retrieval p95 с Cloud.ru cross-encoder = 16.7 с; stage p95 DeepSeek listwise в 20-кейсовом бенчмарке = 6.7 с;
- качество на одних и тех же кейсах: B лучше на +1.7–3.5 п.п.

То есть вывод «Cloud.ru не подходит» нельзя делать из e2e p95 52 с. Корректный вывод: у Cloud.ru cross-encoder пока высокий **собственный** stage p95 (16.7 с), и его надо либо ограничить таймаутом/fallback, либо разворачивать локально. После этого сравнение качества и stage-latency нужно повторить. Production пока остаётся на DeepSeek из-за stage p95, а не из-за e2e-хвоста.





## 8. Ограничения текущей оценки

- **Маленькая выборка.** 60 answerable-кейсов дают широкий доверительный интервал; выводы о разнице режимов до 5–10 п.п. ненадёжны.
- **Один ожидаемый источник на кейс.** Recall — это hit rate; set recall и полноценный nDCG не проверены.
- **Совпадение по clause без привязки к source_id.** Возможны ложные попадания по общим номерам пунктов.
- **Фильтр по типу документа.** Baseline с фильтром и без него совпал, но другие наборы запросов могут вести себя иначе.
- **No-answer retrieval не работает без порога.** `search_min_score = 0.0` гарантирует непустую выдачу; answer-контур отказывается от ответа, но precision падает из-за ложных отказов на answerable.
- **Answer-метрики — pre-chunking baseline.** 20% answerable-кейсов не имеют ожидаемого пункта в контексте; 23 из 35 ложных отказов произошли при наличии пункта, то есть связаны с citations/промптом, а не только с чанкингом.
- **Citation precision низкая.** Модель указывает `source_id` с пунктом, отсутствующим в конкретном чанке; production-валидация такие citations отбрасывает и переводит ответ в `found = false`.
- **Rerank нестабилен.** 22 из 70 кейсов ушли в fallback; это меняет порядок контекста и требует отдельного исправления промпта/модели/JSON-режима.
- **E2E latency с кэшем нерепрезентативна.** Без кэша p95 ≈ 34 с; с кэшем — ~0.18 с p50.
- **Нет разбивки latency на cold/warm.** Первый запрос после старта может искажать p95.
- **LLM-judge подвержен bias.** Нужны калибровка, фиксированные промпты и ручная выборка.

## 9. Нужны ли ragas или DeepEval

Для текущего этапа — нет.

- Retrieval-метрики уже реализованы в `rag_service.eval` без внешних зависимостей.
- Citation validity в проекте проверяется детерминированно; это надёжнее LLM-судьи.
- `ragas` и `DeepEval` добавляют тяжёлые зависимости (`langchain`, `datasets`) и требуют адаптации judge под русский язык и DeepSeek.
- Answer-контур уже реализован в `tools/llm_eval`: RAG → production-промпт → DeepSeek → детерминированная проверка citations → LLM-judge по рубрике → JSON/Markdown-отчёт.

`ragas` имеет смысл добавить позже как optional dev-зависимость, если понадобятся стандартные `faithfulness`, `answer_relevancy`, `context_precision`/`context_recall` для сравнения с внешними бенчмарками. В CI эти прогоны не включаются из-за стоимости и недетерминированности LLM.

## 10. Политика: без зарубежных моделей >1B

Проверка production-контура:

| Компонент | Модель | Происхождение | Размер | Статус |
|---|---|---|---:|---|
| Embeddings | `ai-sage/Giga-Embeddings-instruct-480M` | domestic (Cloud.ru/ai-sage) | 480M | соответствует |
| RAG cross-encoder | `BAAI/bge-reranker-v2-m3` | foreign | 568M | <1B, выключен; если запрещены все foreign — удалить |
| Listwise rerank + answer | `GigaChat/GigaChat-3-Pro` | domestic | не раскрыт | соответствует |
| DeepSeek (старый контур) | `deepseek-v4-flash` / `deepseek-chat` | foreign | >1B | **удалён из production** |

Полный eval domestic-контура (`GigaChat-3-Pro` для listwise и answer, 70 кейсов):

| Метрика | DeepSeek | GigaChat-3-Pro |
|---|---:|---:|
| found_rate | 0.9333 | **0.9833** |
| false_refusals | 4 | **1** |
| citation_precision | 0.8111 | **0.8804** |
| citation_recall | 0.8333 | **0.8833** |
| citation_accuracy | 0.8929 | **0.8983** |
| correctness | 0.9123 | **0.9417** |
| groundedness | 1.0000 | 0.9536 |
| no_answer_precision | 0.7143 | **0.9091** |
| no_answer_recall | 1.0000 | 1.0000 |
| e2e p50 / p95 | 6.2 / 13.1 с | **3.18 / 6.22 с** |

`GigaChat3-10B` проверен отдельно: быстрый (p50 1.35 с), но качество заметно ниже (found 0.65, correctness 0.575), поэтому выбран `GigaChat-3-Pro`.

1С переключён в коде: `ВызватьИИ` использует `foundation-models.api.cloud.ru`, модель принудительно `GigaChat/GigaChat-3-Pro`; seed-промпты обновлены. Для запуска нужно:

1. заполнить ключ Cloud.ru в `rag-service/.env` (ключ хранится только в env, не в базе и не в репозитории);
2. обновить активный промпт `ОтветПоБазеЗнаний` в базе до labels-only (runtime-инструкция уже есть);
3. опубликовать расширение и прогнать ручной e2e из 1С.

## 11. Метрики документов документооборота

С 2026-11-07 `rag_service.eval` поддерживает `scope=documents` и три метрики, которых нет в корпусе знаний:

| Метрика | Определение | Цель |
|---|---|---:|
| `stale_version_leak_rate` | Доля кейсов с непустым `stale_source_ids`, в top-k которых попала старая редакция. Устаревание определяется по `source_id`, `is_current=false` или `status=superseded`. | 0 |
| `acl_leak_rate` | Доля кейсов с непустым `forbidden_source_ids`, в top-k которых попал недоступный документ. | 0 |
| `current_version_accuracy` | Доля documents-кейсов, где top-1 результат совпал с `expected_source_ids`, то есть с актуальной редакцией. | ≥ 0,85 |

Знаменатели:

- `stale_cases` — кейсы, где golden set явно перечислил старые `source_id`;
- `acl_cases` — кейсы, где golden set явно перечислил недоступные `source_id`;
- `current_version_cases` — documents-кейсы с `expected_source_ids` и `no_answer=false`.

Если знаменатель zero, метрика возвращает `0.0`, поэтому в отчёте нужно смотреть пары «метрика + число кейсов». Устаревшая версия и ACL-утечка считаются по top-k после группировки по источнику; `is_current` проверяется и на уровне результата, и на уровне чанка, потому что `/v1/retrieve` с `group_by_source=true` отдаёт чанки внутри результата.

Формат `documents.jsonl` и запуск описаны в `rag-service/eval/README.md`. Первый срез `documents.jsonl` (2026-11-07) собран по 31 утверждённому внутреннему документу реальной базы: 23 кейса, Recall@10 = 1.000, MRR@10 = 0.974, nDCG@10 = 0.981, `current_version_accuracy` = 0.947, `stale_version_leak_rate` = 0, `acl_leak_rate` = 0; no-answer accuracy остаётся 0.000 из-за `search_min_score = 0.0`. До появления реальных данных метрики проверялись unit-тестами `rag-service/tests/test_eval.py` на синтетических ответах.
