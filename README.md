# ai_scrivener

ИИ-помощник должностного лица: конфигурация 1С:Предприятие 8.3, RAG-сервис на Python и Qdrant.

## Документы

- `docs/raw_specification.md` — исходная спецификация.
- `docs/implementation_plan.md` — план реализации.
- `docs/requirements/functional_requirements.md` — функциональные требования.
- `docs/requirements/nonfunctional_requirements.md` — нефункциональные требования.
- `docs/requirements/traceability_matrix.md` — матрица трассируемости.
- `docs/development.md` — инженерные правила и локальные проверки.

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

## Статус

Сформированы требования, матрица трассируемости, конфигурация числовых параметров и пре-коммит-проверки. Реализация 1С-конфигурации и RAG-сервиса начинается после установки 1C:EDT и согласования предложенных требований FR-040 и FR-041.
