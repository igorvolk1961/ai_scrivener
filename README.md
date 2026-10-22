# ai_scrivener

ИИ-помощник должностного лица: расширение 1С:Документооборот 2.1.38.11, RAG-сервис на Python и Qdrant.

## Документы

- `docs/raw_specification.md` — исходная спецификация.
- `docs/implementation_plan.md` — план реализации.
- `docs/requirements/functional_requirements.md` — функциональные требования.
- `docs/requirements/nonfunctional_requirements.md` — нефункциональные требования.
- `docs/requirements/traceability_matrix.md` — матрица трассируемости.
- `docs/development.md` — инженерные правила и локальные проверки.
- `docs/runbook.md` — как самому запускать платформу, базу, Конфигуратор, EDT, расширение и RAG-сервис.
- `docs/postgresql.md` — PostgreSQL для 1С: требования, `mchar`, серверный кластер и ограничения.
- `docs/versioning.md` — источник истины, артефакты, пересборка базы и релизный цикл.

## Требования и конфигурация

Источник истины требований — `docs/requirements/requirements.yaml`. Markdown-документы и матрица генерируются.

Все настраиваемые числовые параметры хранятся в `config/parameters.yaml` и проверяются по `config/parameters.schema.json`.

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

Пользователь базы — `Администратор`, пароль пустой. Подробная инструкция со всеми путями, EDT, расширением и RAG — в `docs/runbook.md`.

## Статус

Сформированы требования, матрица трассируемости, конфигурация числовых параметров и пре-коммит-проверки. Реализован RAG-сервис: FastAPI, GigaChat Embeddings (`EmbeddingsGigaR`, 2560), Qdrant, API индексации и поиска, тесты. Проверен реальный сценарий: 3 шаблона проиндексированы, поиск вернул релевантный первым.

Проект разрабатывается как расширение 1С:Документооборот 2.1.38.11, редакция ПРОФ (`ДокументооборотПРОФ`). Лицензия 8.3.27 активирована, демо-база `DocMng_2_1_38_11_new.dt` восстановлена в файловую базу и в серверную базу PostgreSQL (`ai_scrivener`, 1363 таблицы). Базовая конфигурация импортирована в EDT. В расширении уже созданы перечисления состояний задач и способов заполнения, справочники типов триггеров и действий, регистр `АИС_ЗадачиРеакции`. Стенд предназначен для разработки и проверки, не для промышленной эксплуатации.

Полный порядок запуска платформы, базы, Конфигуратора, EDT, расширения и RAG-сервиса — в `docs/runbook.md`.

Установка 1C:EDT требует прав администратора:

```bash
sudo bash scripts/setup/install_edt.sh
```

EDT 2026.1.3 установлен. Импорт базовой конфигурации, создание расширения и проверки описаны в `docs/development.md`.
