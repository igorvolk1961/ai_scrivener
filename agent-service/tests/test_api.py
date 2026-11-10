from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from agent_service.config import Settings
from agent_service.main import create_app

TOKEN = "test-token"


class FakeLlm:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_request: dict[str, Any] | None = None

    async def complete(self, **kwargs: Any) -> dict[str, Any]:
        self.last_request = kwargs
        return self.response


def make_client(response: dict[str, Any]) -> tuple[TestClient, FakeLlm]:
    llm = FakeLlm(response)
    app = create_app(
        settings=Settings(
            service_token=TOKEN,
            llm_api_key="secret",
            llm_base_url="https://example.invalid",
            request_timeout_seconds=1.0,
        ),
        llm=llm,
    )
    return TestClient(app), llm


def payload(allowed_tools: list[str] | None = None) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "run_version": 7,
        "task": {"id": "task-1", "title": "Тест"},
        "agent": {"login": "ivanov"},
        "llm": {"model": "deepseek-chat", "temperature": 0.2, "max_tokens": 1000},
        "allowed_tools": allowed_tools or ["search_example"],
    }


def test_tool_call() -> None:
    client, llm = make_client(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "search_example",
                                    "arguments": '{"query":"приказ"}',
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )
    response = client.post(
        "/v1/agent/step",
        json=payload(),
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "tool_call"
    assert body["tool"] == "search_example"
    assert body["arguments"] == {"query": "приказ"}
    assert body["run_version"] == 7
    assert llm.last_request is not None


def test_prompt_layers() -> None:
    client, llm = make_client({"choices": [{"message": {"content": "Готово"}}]})
    body = payload()
    body["agent"] = {
        "login": "ivanov",
        "base_prompt": "БАЗОВЫЙ ПРОМПТ",
        "company_profile": "ПРОФИЛЬ КОМПАНИИ",
        "role_prompt": "РОЛЬ СОТРУДНИКА",
    }
    response = client.post(
        "/v1/agent/step",
        json=body,
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    assert llm.last_request is not None
    messages = llm.last_request["messages"]
    system = messages[0]
    assert system["role"] == "system"
    assert "БАЗОВЫЙ ПРОМПТ" in system["content"]
    assert "ПРОФИЛЬ КОМПАНИИ" in system["content"]
    assert "РОЛЬ СОТРУДНИКА" in system["content"]
    user = messages[-1]["content"]
    assert "base_prompt" not in user
    assert "company_profile" not in user
    assert "role_prompt" not in user


def test_final_answer() -> None:
    client, _ = make_client({"choices": [{"message": {"content": "Готово"}}]})
    response = client.post(
        "/v1/agent/step",
        json=payload(),
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "final"


def test_unknown_tool_rejected() -> None:
    client, _ = make_client(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "delete_everything",
                                    "arguments": "{}",
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )
    response = client.post(
        "/v1/agent/step",
        json=payload(),
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "error"
    assert response.json()["code"] == "tool_not_allowed"


def test_no_token_required() -> None:
    client, _ = make_client({"choices": [{"message": {"content": "Готово"}}]})
    response = client.post("/v1/agent/step", json=payload())
    assert response.status_code == 200


def test_health() -> None:
    client, _ = make_client({"choices": []})
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
