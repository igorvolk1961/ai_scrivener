# agent-service

Stateless-планировщик ИИ-агента для расширения `ai_scrivener`.

Сервис вызывает LLM и возвращает один `tool_call` или `final`. Инструменты, права,
approval и изменения данных выполняет 1С.

## Переменные окружения

- `AGENT_SERVICE_TOKEN` — service-token для запросов из 1С.
- `LLM_API_KEY` — ключ LLM.
- `LLM_BASE_URL` — OpenAI-совместимый endpoint, по умолчанию `https://api.deepseek.com`.
- `AGENT_REQUEST_TIMEOUT` — таймаут запроса к LLM, секунды.

Модель, температура и лимит токенов приходят в теле запроса из 1С.

## Запуск

```bash
uv run --project agent-service python -m agent_service
```

## API

- `GET /health`
- `POST /v1/agent/step` с заголовком `X-Service-Token`.
