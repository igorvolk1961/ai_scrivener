from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_service.config import Settings, load_settings
from agent_service.llm import LlmClient, LlmError
from agent_service.models import CompleteRequest, CompleteResponse, StepRequest
from agent_service.prompts import SYSTEM_PROMPT
from agent_service.tools import tool_definitions, validate_tool_name

logger = logging.getLogger("uvicorn.error")


def _error(run_version: int, code: str, message: str) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "run_version": run_version,
        "type": "error",
        "code": code,
        "message": message,
    }


def _system_prompt(agent: dict[str, Any]) -> str:
    base = str(agent.get("base_prompt") or "").strip() or SYSTEM_PROMPT
    parts = [base]
    company = str(agent.get("company_profile") or "").strip()
    if company:
        parts.append("Профиль компании:\n" + company)
    role = str(agent.get("role_prompt") or "").strip()
    if role:
        parts.append(
            "Описание твоей роли, подготовленное отделом кадров при найме:\n" + role
        )
    return "\n\n".join(parts)


def _context_message(payload: StepRequest) -> dict[str, Any]:
    agent = {
        key: value
        for key, value in payload.agent.items()
        if key not in {"base_prompt", "company_profile", "role_prompt"}
    }
    context = {
        "task": payload.task,
        "agent": agent,
        "context": payload.context,
        "policy": payload.policy,
    }
    return {
        "role": "user",
        "content": json.dumps(context, ensure_ascii=False),
    }


def _drop_unresolved_tool_calls(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove assistant tool calls that have no matching tool result.

    A run resumed after its approval interaction expired keeps the last
    assistant message with a tool call but no tool response. LLM providers
    reject such a history with HTTP 400, so the retry never reaches the model.
    """

    resolved = {
        str(message["tool_call_id"])
        for message in messages
        if message.get("role") == "tool" and message.get("tool_call_id")
    }
    sanitized: list[dict[str, Any]] = []
    for message in messages:
        tool_calls = message.get("tool_calls")
        if message.get("role") != "assistant" or not isinstance(tool_calls, list):
            sanitized.append(message)
            continue
        kept = [
            call
            for call in tool_calls
            if isinstance(call, dict) and str(call.get("id")) in resolved
        ]
        if not kept:
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                copy = dict(message)
                copy.pop("tool_calls", None)
                sanitized.append(copy)
            continue
        if len(kept) == len(tool_calls):
            sanitized.append(message)
        else:
            sanitized.append({**message, "tool_calls": kept})
    return sanitized


def _parse_arguments(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_response(data: dict[str, Any]) -> dict[str, Any] | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    return message


def create_app(
    settings: Settings | None = None,
    llm: LlmClient | None = None,
) -> FastAPI:
    app = FastAPI(title="ai-scrivener-agent", version="0.1.0")
    app.state.settings = settings or load_settings()
    if llm is not None:
        app.state.llm = llm
    else:
        from agent_service.llm import HttpLlmClient

        app.state.llm = HttpLlmClient(
            app.state.settings.llm_base_url,
            app.state.settings.llm_api_key,
            app.state.settings.request_timeout_seconds,
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        current: Settings = request.app.state.settings
        return {
            "status": "ok",
            "version": current.version,
            "provider": "openai-compatible",
            "key_configured": bool(current.llm_api_key),
        }

    @app.post("/v1/llm/complete", response_model=None)
    async def complete(
        request: Request,
        payload: CompleteRequest,
    ) -> CompleteResponse | JSONResponse:
        system_prompt = payload.system_prompt.strip()
        if payload.json_mode:
            system_prompt += "\n\nВерни только валидный JSON без markdown."
        client: LlmClient = request.app.state.llm
        try:
            data = await client.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload.user_prompt},
                ],
                tools=[],
                model=payload.model,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        except LlmError as exc:
            return JSONResponse(status_code=502, content={"detail": str(exc)})
        message = _parse_response(data)
        content = message.get("content") if message else None
        if not isinstance(content, str) or not content.strip():
            return JSONResponse(status_code=502, content={"detail": "empty llm response"})
        return CompleteResponse(
            content=content,
            model=str(data.get("model") or payload.model),
        )

    @app.post("/v1/agent/step")
    async def step(
        request: Request,
        payload: StepRequest,
    ) -> JSONResponse:
        if payload.protocol_version != 1:
            return JSONResponse(
                content=_error(
                    payload.run_version,
                    "unsupported_protocol",
                    "protocol_version must be 1",
                )
            )

        client: LlmClient = request.app.state.llm
        messages = [
            {"role": "system", "content": _system_prompt(payload.agent)},
            *_drop_unresolved_tool_calls(payload.messages),
            _context_message(payload),
        ]
        tools = tool_definitions(payload.allowed_tools)
        logger.info(
            "agent step run_version=%s model=%s messages=%s",
            payload.run_version,
            payload.llm.model,
            len(messages),
        )
        try:
            data = await client.complete(
                messages=messages,
                tools=tools,
                model=payload.llm.model,
                temperature=payload.llm.temperature,
                max_tokens=payload.llm.max_tokens,
            )
        except LlmError as exc:
            return JSONResponse(
                status_code=502,
                content={"detail": str(exc)},
            )

        message = _parse_response(data)
        if message is None:
            return JSONResponse(
                content=_error(payload.run_version, "invalid_response", "empty llm response")
            )

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            call = tool_calls[0]
            if not isinstance(call, dict):
                return JSONResponse(
                    content=_error(payload.run_version, "invalid_response", "invalid tool call")
                )
            function = call.get("function")
            if not isinstance(function, dict):
                return JSONResponse(
                    content=_error(payload.run_version, "invalid_response", "invalid tool function")
                )
            name = str(function.get("name") or "")
            arguments = _parse_arguments(function.get("arguments"))
            if not validate_tool_name(name, payload.allowed_tools):
                return JSONResponse(
                    content=_error(
                        payload.run_version,
                        "tool_not_allowed",
                        f"tool not allowed: {name}",
                    )
                )
            if arguments is None:
                return JSONResponse(
                    content=_error(
                        payload.run_version,
                        "invalid_arguments",
                        "invalid tool arguments",
                    )
                )
            logger.info(
                "agent step run_version=%s tool=%s arguments=%s",
                payload.run_version,
                name,
                json.dumps(arguments, ensure_ascii=False)[:1000],
            )
            return JSONResponse(
                content={
                    "protocol_version": 1,
                    "run_version": payload.run_version,
                    "type": "tool_call",
                    "call_id": str(call.get("id") or secrets.token_hex(8)),
                    "tool": name,
                    "arguments": arguments,
                }
            )

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return JSONResponse(
                content={
                    "protocol_version": 1,
                    "run_version": payload.run_version,
                    "type": "final",
                    "content": content,
                }
            )
        return JSONResponse(
            content=_error(payload.run_version, "invalid_response", "empty llm message")
        )

    return app
