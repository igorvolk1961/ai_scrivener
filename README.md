# ai_scrivener

ИИ-помощник должностного лица: расширение 1С:Документооборот 2.1.38.11, RAG-сервис на Python и Qdrant.

## Документы

- `docs/raw_specification.md` — исходная спецификация.
- `docs/system-analysis/view-and-scope.md` — видение и границы проекта (Vision & Scope).
- `docs/system-analysis/glossary.md` — глоссарий.
- `docs/system-analysis/stakeholder-map.md` — карта стейкхолдеров.
- `docs/system-analysis/use-cases.md` — варианты использования.
- `docs/system-analysis/c4-model.md` — C4-модель: контекст, контейнеры и компоненты.
- `docs/requirements/functional_requirements.md` — функциональные требования.
- `docs/requirements/nonfunctional_requirements.md` — нефункциональные требования.
- `docs/requirements/traceability_matrix.md` — матрица трассируемости.
- `docs/data-model.md` — дедуплицированная модель: какие объекты базы переиспользуются и что создаётся в расширении.
- `docs/process-diagrams.md` — процессные диаграммы AS-IS и TO-BE.
- `docs/template-factory.md` — мастер шаблонов: импорт DOCX, AI-разметка, автогенерация правил.
- `docs/proofreading.md` — вычитка документов: быстрая проверка, LLM-вычитка, квоты.
- `docs/design-decisions.md` — завершённые проектные решения и закрытые вопросы.

## Планы и ревью

- `plans/implementation_plan.md` — план реализации.
- `plans/` — рабочие планы: `stage2-plan.md`, `remediation-plan.md` и планы сессий.
- `reviews/` — результаты ревью внешними ИИ-агентами: `critical-review.md`.

## Руководства

- `guides/development.md` — инженерные правила и локальные проверки.
- `guides/dev-environment.md` — среда разработки: AI-агенты, инструменты, 1С, Docker и CI.
- `guides/runbook.md` — как самому запускать платформу, базу, Конфигуратор, EDT, расширение и RAG-сервис.
- `guides/postgresql.md` — PostgreSQL для 1С: требования, `mchar`, серверный кластер и ограничения.
- `guides/versioning.md` — источник истины, артефакты, пересборка базы и релизный цикл.

## Требования и конфигурация

Источник истины требований — `docs/requirements/requirements.yaml`. Markdown-документы и матрица генерируются.

Все настраиваемые числовые параметры хранятся в `config/parameters.yaml` и проверяются по `config/parameters.schema.json`.

Согласованные заглушки — только через `TODO.md`: заглушка в коде без ссылки на существующую запись `TODO.md#T-NNN` блокируется пре-коммитом (`guides/development.md` §4).

## Проверки

```bash
uv sync
uv run pre-commit install
make requirements
make check
```

## Быстрый запуск

```bash
export ONEC=/opt/1cv8/x86_64/8.3.27.2342/1cv8
export IB=/home/igorvolk/1C/ai_scrivener_docmng

"$ONEC"                       # окно запуска 1С
"$ONEC" DESIGNER /F"$IB" /N Администратор   # Конфигуратор
"$ONEC" ENTERPRISE /F"$IB" /N Администратор # 1С:Предприятие

bash scripts/run/1c.sh        # то же через обёртку; запускать bash, не sh
bash scripts/run/1c.sh designer
bash scripts/run/1c.sh enterprise
bash scripts/run/1c.sh check

bash scripts/run/1c.sh pg-enterprise  # серверная база PostgreSQL
bash scripts/run/1c.sh pg-designer
bash scripts/run/1c.sh pg-db          # psql к базе 1С
bash scripts/run/1c-pg-server.sh      # PostgreSQL + кластер 1С в одном терминале
bash scripts/run/1c-pg-server.sh stop # остановить PostgreSQL и кластер

./scripts/build/export_extension.sh   # src → EDT-копия → XML
./scripts/build/load_extension.sh server # XML → серверная база
```

Пользователь базы — `Администратор`, пароль пустой. Подробная инструкция со всеми путями, EDT, расширением и RAG — в `guides/runbook.md`.

## Статус

Сформированы требования, матрица трассируемости, конфигурация числовых параметров и пре-коммит-проверки. Реализована инфраструктура RAG-сервиса (naive RAG): FastAPI, GigaChat Embeddings (`EmbeddingsGigaR`, 2560), Qdrant, API индексации и поиска, тесты. Проверен сценарий на 3 шаблонах — поиск вернул релевантный первым; это подтверждает работу инфраструктуры на маленьком корпусе, а не качество поиска в целом. Известные ограничения подхода (чанкинг без учёта структуры, отсутствие гибридного поиска и reranker, неоткалиброванный confidence LLM) задокументированы в `reviews/critical-review.md` §3 и не устранены — решено исправлять по мере роста корпуса шаблонов (`docs/design-decisions.md` §18), не сейчас.

Проект разрабатывается как расширение 1С:Документооборот 2.1.38.11, редакция ПРОФ (`ДокументооборотПРОФ`). Лицензия 8.3.27 активирована, демо-база `DocMng_2_1_38_11_new.dt` восстановлена в файловую базу и в серверную базу PostgreSQL (`ai_scrivener`, 1363 таблицы). Базовая конфигурация импортирована в EDT. Метаданные Этапа 2 в основном созданы и проверены реальной сборкой через EDT CLI: 8 перечислений, 3 определяемых типа, 7 справочников (включая `АИС_РазделыДокумента`, `АИС_ЛистОжидания`, `АИС_РасписаниеТриггеров` — справочники, не регистры, см. `docs/data-model.md`), 4 регистра сведений. Этап A синхронизации выполнен: добавлены `РешениеДЛ`, `Список` и ресурс `СсылкаНаРаздел`; EDT build/validate проходят без ошибок, остаются только minor style warnings. Не сделаны: ТЧ `АИС_Плейсхолдеры` в штатных справочниках шаблонов, роли (кроме заглушки), RLS, параметр сеанса, демоданные, а также вся бизнес-логика (общие модули, формы, регламентные задания) — это Этапы 2 (остаток) и 4–6, подробности в `plans/stage2-plan.md`. Стенд предназначен для разработки и проверки, не для промышленной эксплуатации.

Проектирование завершено: решения по шаблонам, сравнению, разделам, вычитке и квотам зафиксированы в `docs/design-decisions.md`.

Полный порядок запуска платформы, базы, Конфигуратора, EDT, расширения и RAG-сервиса — в `guides/runbook.md`.

Установка 1C:EDT требует прав администратора:

```bash
sudo bash scripts/setup/install_edt.sh
```

EDT 2026.1.3 установлен. Импорт базовой конфигурации, создание расширения и проверки описаны в `guides/development.md`.
