from __future__ import annotations

import hmac
import json
import secrets
from typing import Annotated, Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from agent_service.config import Settings, load_settings
from agent_service.llm import LlmClient, LlmError
from agent_service.models import StepRequest
from agent_service.prompts import SYSTEM_PROMPT
from agent_service.tools import tool_definitions, validate_tool_name


def _token_valid(settings: Settings, value: str | None) -> bool:
    return value is not None and hmac.compare_digest(value, settings.service_token)


def _error(run_version: int, code: str, message: str) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "run_version": run_version,
        "type": "error",
        "code": code,
        "message": message,
    }


def _context_message(payload: StepRequest) -> dict[str, Any]:
    context = {
        "task": payload.task,
        "agent": payload.agent,
        "context": payload.context,
        "policy": payload.policy,
    }
    return {
        "role": "user",
        "content": json.dumps(context, ensure_ascii=False),
    }


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

    @app.post("/v1/agent/step")
    async def step(
        request: Request,
        payload: StepRequest,
        x_service_token: Annotated[str | None, Header()] = None,
    ) -> JSONResponse:
        current: Settings = request.app.state.settings
        if not _token_valid(current, x_service_token):
            return JSONResponse(status_code=401, content={"detail": "invalid service token"})
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
            {"role": "system", "content": SYSTEM_PROMPT},
            *payload.messages,
            _context_message(payload),
        ]
        tools = tool_definitions(payload.allowed_tools)
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
