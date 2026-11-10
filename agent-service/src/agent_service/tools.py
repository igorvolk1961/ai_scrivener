from __future__ import annotations

from typing import Any

TOOL_DESCRIPTIONS: dict[str, str] = {
    "request_action_approval": "Запросить у пользователя одобрение изменяющего действия.",
    "ask_clarifying_question": "Задать пользователю уточняющий вопрос.",
    "ask_example_changes": "Задать вопросы об изменениях образца документа.",
    "ask_decision": "Запросить решение пользователя по вариантам.",
    "complete_task": "Завершить задачу сотрудника.",
    "search_example": "Найти образец документа в RAG.",
    "search_knowledge_base": "Найти сведения в базе знаний.",
    "search_internet": "Найти сведения в интернете.",
    "save_external_example": "Сохранить внешний образец.",
    "get_checklist": "Получить чек-лист.",
    "get_job_description": "Получить должностную инструкцию.",
    "list_documents": "Показать доступные документы.",
    "read_document": "Прочитать документ.",
    "check_document_access": "Проверить доступ к документу.",
    "create_draft": "Создать черновик документа.",
    "create_information_request": "Создать запрос информации.",
    "submit_draft_for_review": "Отправить черновик на согласование.",
    "create_document": "Создать внутренний документ.",
    "approve_document": "Утвердить документ.",
    "cancel_document": "Отменить документ.",
    "hire_employee": "Принять сотрудника.",
    "propose_system_prompt": "Сформировать роль-промпт агента.",
    "accounting_decision": "Принять решение по зарплатной вилке.",
    "list_employees": "Показать сотрудников.",
    "list_departments": "Показать подразделения.",
    "create_department": "Создать подразделение.",
    "manage_document_sections": "Управлять разделами документа.",
    "manage_remarks": "Управлять замечаниями.",
    "return_document": "Вернуть документ на доработку.",
    "route_remarks": "Направить замечания.",
    "kb_download": "Скачать материал корпуса знаний.",
    "kb_register_material": "Зарегистрировать материал корпуса знаний.",
    "kb_list_materials": "Показать материалы корпуса знаний.",
}

GENERIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": True,
}


def tool_definitions(allowed_tools: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in allowed_tools:
        if name not in TOOL_DESCRIPTIONS:
            continue
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": TOOL_DESCRIPTIONS[name],
                    "parameters": GENERIC_SCHEMA,
                },
            }
        )
    return result


def validate_tool_name(name: str, allowed_tools: list[str]) -> bool:
    return name in allowed_tools and name in TOOL_DESCRIPTIONS
