from __future__ import annotations

from agent_service.tools import tool_definitions, validate_tool_name


def test_tool_definitions_use_specific_schemas() -> None:
    definitions = {
        item["function"]["name"]: item
        for item in tool_definitions(
            ["request_action_approval", "create_document", "unknown_tool"]
        )
    }
    assert set(definitions) == {"request_action_approval", "create_document"}
    approval = definitions["request_action_approval"]["function"]["parameters"]
    assert approval["required"] == ["completed", "intended", "question", "options"]
    create = definitions["create_document"]["function"]["parameters"]
    assert create["required"] == ["title", "document_type"]
    more = {
        item["function"]["name"]: item
        for item in tool_definitions(
            ["list_employees", "list_departments", "get_checklist", "get_job_description"]
        )
    }
    assert set(more) == {
        "list_employees",
        "list_departments",
        "get_checklist",
        "get_job_description",
    }
    assert more["get_job_description"]["function"]["parameters"]["required"] == ["position"]
    personnel = {
        item["function"]["name"]: item
        for item in tool_definitions(
            ["hire_employee", "create_department", "accounting_decision", "propose_system_prompt"]
        )
    }
    assert personnel["hire_employee"]["function"]["parameters"]["required"] == [
        "login",
        "name",
        "position",
    ]
    assert personnel["propose_system_prompt"]["function"]["parameters"]["required"] == [
        "login",
        "system_prompt",
    ]
    sections = tool_definitions(["manage_document_sections"])[0]["function"]["parameters"]
    assert sections["required"] == ["action"]
    assert len(sections["properties"]["action"]["enum"]) == 9
    remarks = tool_definitions(["manage_remarks", "return_document", "route_remarks"])
    assert {item["function"]["name"] for item in remarks} == {
        "manage_remarks",
        "return_document",
        "route_remarks",
    }
    corpus = tool_definitions(["kb_list_materials", "kb_register_material", "kb_download"])
    assert {item["function"]["name"] for item in corpus} == {
        "kb_list_materials",
        "kb_register_material",
        "kb_download",
    }


def test_validate_tool_name() -> None:
    assert validate_tool_name("complete_task", ["complete_task"])
    assert not validate_tool_name("hire_employee", ["complete_task"])
    assert not validate_tool_name("unknown_tool", ["unknown_tool"])
