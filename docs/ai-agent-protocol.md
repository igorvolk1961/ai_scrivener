# Протокол внешнего ИИ-агента

## 1. Назначение

`agent-service` — внешний stateless-планировщик. Он вызывает LLM и возвращает один следующий шаг. Все инструменты, проверки прав, approval и изменения данных выполняет 1С.

## 2. Общие правила

- Один HTTP-запрос — один шаг агента.
- Один шаг возвращает не более одного `tool_call` или `final`.
- Сервис не обращается к API 1С и не хранит состояние между запросами.
- 1С передает полную историю сообщений и актуальный снимок задачи.
- Любой ответ содержит `protocol_version` и `run_version`.
- 1С отклоняет ответ с устаревшим `run_version`.
- Ключ LLM не передается в запросе и не логируется.
- `tool_call` с неизвестным или запрещенным инструментом отклоняется 1С и завершает run с `ТребуетВнимания`.

## 3. Запрос шага

`POST /v1/agent/step`

Заголовки:

- `X-Service-Token: <AGENT_SERVICE_TOKEN>`;
- `Content-Type: application/json`.

Тело:

```json
{
  "protocol_version": 1,
  "run_version": 7,
  "task": {
    "id": "uuid",
    "title": "Подготовить приказ",
    "description": "Текст задачи",
    "executor": "ivanov",
    "author": "petrov",
    "due_at": "2026-11-11T18:00:00+03:00",
    "subject": {
      "type": "ВнутреннийДокумент",
      "id": "uuid",
      "title": "Приказ от 10.11.2026"
    }
  },
  "agent": {
    "login": "ivanov",
    "position": "Главный бухгалтер",
    "role_prompt": "Ты главный бухгалтер..."
  },
  "context": {
    "trigger": "НовыйДокумент",
    "action": "ПодготовитьПроект",
    "candidates": [],
    "approval": {}
  },
  "messages": [
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [
        {
          "id": "call_1",
          "type": "function",
          "function": {"name": "search_example", "arguments": "{\"query\":\"...\"}"}
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_1",
      "content": "{\"ok\":true,\"data\":{...}}"
    }
  ],
  "llm": {
    "model": "deepseek-chat",
    "temperature": 0.2,
    "max_tokens": 2000
  },
  "allowed_tools": ["search_example", "create_draft"],
  "policy": {
    "approval_gate": true,
    "allowed_addressees": [],
    "web_search": true,
    "knowledge": true,
    "max_steps": 20
  }
}
```

## 4. Ответ шага

### 4.1. Вызов инструмента

```json
{
  "protocol_version": 1,
  "run_version": 7,
  "type": "tool_call",
  "call_id": "call_1",
  "tool": "search_example",
  "arguments": {"query": "приказ о создании отдела"}
}
```

### 4.2. Финальный ответ

```json
{
  "protocol_version": 1,
  "run_version": 7,
  "type": "final",
  "content": "Задача выполнена."
}
```

`final` не завершает задачу. Задачу завершает отдельный инструмент `complete_task`.

### 4.3. Ошибка

```json
{
  "protocol_version": 1,
  "run_version": 7,
  "type": "error",
  "code": "llm_error",
  "message": "Провайдер вернул ошибку"
}
```

Коды:

- `llm_error`;
- `invalid_response`;
- `tool_not_allowed`;
- `invalid_arguments`;
- `approval_required`;
- `service_error`.

## 5. Результат инструмента

После выполнения 1С добавляет в историю сообщение:

```json
{
  "role": "tool",
  "tool_call_id": "call_1",
  "content": "{\"ok\":true,\"data\":{...},\"interaction_id\":null}"
}
```

При ошибке:

```json
{
  "role": "tool",
  "tool_call_id": "call_1",
  "content": "{\"ok\":false,\"error\":{\"code\":\"access_denied\",\"message\":\"Нет доступа к документу\"}}"
}
```

## 6. Взаимодействие с пользователем

Инструменты `request_action_approval`, `ask_clarifying_question`, `ask_example_changes`, `ask_decision`, `submit_draft_for_review` создают запись `АИС_ВзаимодействияИИ` и останавливают run в состоянии `ОжидаетОтвета`.

После ответа 1С формирует tool result:

```json
{
  "ok": true,
  "data": {
    "interaction_id": "uuid",
    "decision": "approved",
    "answer": {}
  }
}
```

и запускает следующий шаг с тем же `run_version + 1`.

### 6.1. Контракт `request_action_approval`

Обязательные аргументы:

```json
{
  "completed": "что уже сделано",
  "intended": "что планируется сделать",
  "question": "вопрос пользователю",
  "options": [
    {"kind": "approve", "text": "Одобряю. Действуй"},
    {"kind": "free_text", "text": "Отклонить и указать, что изменить"}
  ],
  "documents": [
    {"document_id": null, "title": "...", "document_type": "...", "text": "полный текст"}
  ],
  "subject_kind": "documents",
  "tool": null,
  "arguments": null
}
```

Для изменяющего действия без документа используется `subject_kind = "action"`, а `tool` и `arguments` обязательны. Любой свободный текст ответа трактуется как отклонение.

### 6.2. Approval state в 1С

`АИС_ЗапускиАгентов.ОдобрениеJSON` хранит:

```json
{
  "subject_kind": "documents | action",
  "tool": "create_document",
  "args_hash": "sha256",
  "args_json": "{...}",
  "decision": "approved | rejected",
  "answer_text": "",
  "interaction_id": "uuid",
  "consumed": false,
  "created_at": "..."
}
```

Для `documents` разрешены только документные инструменты; для `action` требуется совпадение инструмента и хеша аргументов. После успешного изменяющего действия `consumed = true` и требуется новое одобрение.

## 7. Снимок задачи

1С передает только данные, доступные исполнителю:

- задачу и предмет;
- контекст `АИС_КонтекстЗадачИИ`;
- роль-промпт;
- историю шагов;
- approval state;
- разрешенные инструменты;
- ACL-фильтр документов и адресатов.

Запрещено передавать:

- пароли, токены и ключи;
- документы, недоступные исполнителю;
- лишние персональные данные;
- полные тексты, если достаточно идентификатора и фрагмента.

## 8. Версионирование

- `protocol_version` увеличивается при несовместимом изменении контракта.
- `run_version` увеличивается на каждом шаге и при каждом ответе пользователя.
- `agent-service` возвращает версию, полученную в запросе; менять ее нельзя.
- 1С хранит версию в `АИС_ЗапускиАгентов` и отклоняет устаревшие ответы.
