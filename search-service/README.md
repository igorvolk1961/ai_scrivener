# search-service

Внешний read-only поисковый сервис для `ai_scrivener`.

Вызывается из 1С по `POST /v1/search` с заголовком `X-Service-Token`.
Сервис не имеет доступа к 1С и возвращает только результаты поиска.

## Переменные окружения

- `SEARCH_SERVICE_TOKEN` — service-token для 1С (обязателен).
- `SEARCH_TIMEOUT` — таймаут провайдера, секунды (по умолчанию 20).
- `SEARCH_MAX_RESULTS` — ограничение результатов на запрос, 1–20 (по умолчанию 10).
- `SEARCH_PROVIDER` — провайдер поиска; на MVP поддерживается `duckduckgo`.

## Запуск

```bash
uv run --project search-service python -m search_service
```
