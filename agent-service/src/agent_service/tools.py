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

DOCUMENT_ID = {
    "type": "string",
    "description": "UUID документа из list_documents.",
}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "request_action_approval": {
        "type": "object",
        "properties": {
            "completed": {"type": "string", "description": "Что уже сделано."},
            "intended": {"type": "string", "description": "Что планируется сделать."},
            "question": {"type": "string", "description": "Вопрос пользователю."},
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["approve", "free_text"]},
                        "text": {"type": "string"},
                    },
                    "required": ["kind", "text"],
                },
            },
            "documents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": ["string", "null"]},
                        "title": {"type": "string"},
                        "document_type": {"type": "string"},
                        "text": {"type": "string"},
                        "author": {"type": ["string", "null"]},
                        "counterparty": {"type": ["string", "null"]},
                    },
                    "required": ["title", "document_type", "text"],
                },
            },
            "subject_kind": {"type": "string", "enum": ["documents", "action"]},
            "tool": {
                "type": "string",
                "description": "Имя изменяющего инструмента для subject_kind=action.",
            },
            "arguments": {
                "type": "object",
                "description": "Аргументы планируемого действия для subject_kind=action.",
            },
        },
        "required": ["completed", "intended", "question", "options"],
    },
    "ask_clarifying_question": {
        "type": "object",
        "properties": {
            "context": {"type": "string"},
            "question": {"type": "string"},
        },
        "required": ["question"],
    },
    "complete_task": {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    },
    "search_example": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "document_kind": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
    "search_knowledge_base": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
    "search_internet": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    },
    "get_checklist": {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "description": (
                    "Назначение чек-листа; по умолчанию разработка должностной инструкции."
                ),
            }
        },
    },
    "get_job_description": {
        "type": "object",
        "properties": {
            "position": {"type": "string", "description": "Наименование должности."}
        },
        "required": ["position"],
    },
    "list_employees": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
    },
    "list_departments": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
    },
    "list_documents": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
    },
    "read_document": {
        "type": "object",
        "properties": {"document_id": DOCUMENT_ID},
        "required": ["document_id"],
    },
    "check_document_access": {
        "type": "object",
        "properties": {"document_id": DOCUMENT_ID},
        "required": ["document_id"],
    },
    "create_draft": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "document_type": {"type": "string"},
            "addressee": {"type": "string"},
            "basis_id": DOCUMENT_ID,
            "draft_kind": {"type": "string"},
            "request_kind": {"type": "string"},
            "source_documents": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title"],
    },
    "create_information_request": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "document_type": {"type": "string"},
            "addressee": {"type": "string"},
            "basis_id": DOCUMENT_ID,
            "request_kind": {"type": "string"},
            "source_documents": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title"],
    },
    "submit_draft_for_review": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "text": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title"],
    },
    "hire_employee": {
        "type": "object",
        "properties": {
            "login": {"type": "string"},
            "name": {"type": "string", "description": "ФИО сотрудника."},
            "position": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
            "manager": {"type": "string", "description": "Логин руководителя."},
            "allow_without_manager": {"type": "boolean"},
        },
        "required": ["login", "name", "position"],
    },
    "create_department": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "manager": {"type": "string", "description": "Логин руководителя."},
            "parent": {"type": "string"},
        },
        "required": ["name", "manager"],
    },
    "accounting_decision": {
        "type": "object",
        "properties": {
            "request_id": {"type": "string", "description": "UUID заявки на найм."},
            "decision": {"type": "string", "enum": ["Согласовать", "Отклонить"]},
            "comment": {"type": "string"},
            "updated_text": {"type": "string"},
        },
        "required": ["request_id", "decision"],
    },
    "propose_system_prompt": {
        "type": "object",
        "properties": {"login": {"type": "string"}},
        "required": ["login"],
    },
    "manage_document_sections": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_document",
                    "create_draft",
                    "issue_section_order",
                    "list_sections",
                    "assign_section",
                    "write_section",
                    "create_subsection",
                    "approve_section",
                    "assemble_document",
                ],
            },
            "template_id": {"type": "string"},
            "title": {"type": "string"},
            "kind": {"type": "string"},
            "sections": {"type": "array", "items": {"type": "string"}},
            "order_title": {"type": "string"},
            "instruction": {"type": "string"},
            "document_id": {"type": "string"},
            "section_id": {"type": "string"},
            "parent_section_id": {"type": "string"},
            "employee": {"type": "string"},
            "content": {"type": "string"},
            "submit": {"type": "boolean"},
            "approver": {"type": "string"},
        },
        "required": ["action"],
    },
    "manage_remarks": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "assign", "update", "summary"],
            },
            "document_id": {"type": "string"},
            "document_title": {"type": "string"},
            "owner": {"type": "string"},
            "remark_id": {"type": "string"},
            "remark_ids": {"type": "array", "items": {"type": "string"}},
            "status": {
                "type": "string",
                "enum": ["open", "in_progress", "fixed", "accepted", "rejected"],
            },
            "resolution": {"type": "string"},
            "remarks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "item": {"type": "string"},
                        "text": {"type": "string"},
                        "owner": {"type": "string"},
                        "blocking": {"type": "boolean"},
                        "status": {"type": "string"},
                        "round": {"type": "integer"},
                        "resolution": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": ["action"],
    },
    "return_document": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "document_title": {"type": "string"},
            "addressee": {"type": "string"},
            "summary": {"type": "string"},
            "remarks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "item": {"type": "string"},
                        "text": {"type": "string"},
                        "blocking": {"type": "boolean"},
                        "owner": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": ["document_id", "addressee", "remarks"],
    },
    "route_remarks": {
        "type": "object",
        "properties": {
            "document_id": {"type": "string"},
            "addressee": {"type": "string"},
            "remark_ids": {"type": "array", "items": {"type": "string"}},
            "instruction": {"type": "string"},
        },
        "required": ["document_id", "addressee", "remark_ids"],
    },
    "kb_list_materials": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
    },
    "kb_register_material": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Относительный путь в корпусе знаний."},
            "title": {"type": "string"},
            "source_url": {"type": "string"},
            "source_kind": {
                "type": "string",
                "enum": ["official", "library", "vendor", "other"],
            },
            "authority": {"type": "string"},
            "published_at": {"type": "string"},
            "license": {"type": "string"},
            "doc_type": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["path", "title"],
    },
    "kb_download": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "authority": {"type": "string"},
            "published_at": {"type": "string"},
            "license": {"type": "string"},
            "doc_type": {"type": "string"},
            "source_kind": {
                "type": "string",
                "enum": ["official", "library", "vendor", "other"],
            },
            "notes": {"type": "string"},
        },
        "required": ["url", "title"],
    },
    "create_document": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "document_type": {"type": "string"},
            "addressee": {"type": "string"},
            "basis_id": DOCUMENT_ID,
        },
        "required": ["title", "document_type"],
    },
    "approve_document": {
        "type": "object",
        "properties": {"document_id": DOCUMENT_ID},
        "required": ["document_id"],
    },
    "cancel_document": {
        "type": "object",
        "properties": {
            "document_id": DOCUMENT_ID,
            "basis_id": DOCUMENT_ID,
            "comment": {"type": "string"},
        },
        "required": ["document_id", "basis_id"],
    },
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
                    "parameters": TOOL_SCHEMAS.get(name, GENERIC_SCHEMA),
                },
            }
        )
    return result


def validate_tool_name(name: str, allowed_tools: list[str]) -> bool:
    return name in allowed_tools and name in TOOL_DESCRIPTIONS
