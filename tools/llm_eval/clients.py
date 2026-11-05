from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_CHAT_ATTEMPTS = 3


class HttpError(RuntimeError):
    """HTTP or transport failure while calling an external service."""


class JsonParseError(RuntimeError):
    """The model response does not contain a valid JSON object."""


def load_env_file(path: Path) -> None:
    """Load ``KEY=VALUE`` pairs into os.environ without overriding existing values."""

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: float,
    retries: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **headers}
    last_error: HttpError | None = None

    for attempt in range(retries + 1):
        request = Request(  # noqa: S310
            url, data=body, headers=request_headers, method="POST"
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")[:500]
            last_error = HttpError(f"HTTP {error.code}: {error_body}")
            if error.code not in RETRY_STATUSES or attempt >= retries:
                raise last_error from error
        except URLError as error:
            last_error = HttpError(f"network error: {error.reason}")
            if attempt >= retries:
                raise last_error from error
        except TimeoutError as error:
            last_error = HttpError("request timed out")
            if attempt >= retries:
                raise last_error from error
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                raise HttpError("external service returned invalid JSON") from error
            if not isinstance(parsed, dict):
                raise HttpError("external service returned a non-object JSON")
            return parsed

        time.sleep(min(2**attempt, 8))

    raise last_error or HttpError("request failed")


def cache_key(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class ResponseCache:
    directory: Path

    def get(self, key: str) -> str | None:
        path = self.directory / f"{key}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        content = payload.get("content") if isinstance(payload, dict) else None
        return content if isinstance(content, str) else None

    def put(self, key: str, content: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{key}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"content": content}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)


@dataclass(frozen=True)
class RagClient:
    base_url: str
    token: str
    timeout: float = 90.0

    def retrieve(
        self,
        query: str,
        filters: dict[str, Any],
        *,
        top_k: int | None = None,
        candidate_k: int | None = None,
        group_size: int | None = None,
        include_parent: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "filters": filters}
        if top_k is not None:
            payload["top_k"] = top_k
        if candidate_k is not None:
            payload["candidate_k"] = candidate_k
        if group_size is not None:
            payload["group_size"] = group_size
        if include_parent is not None:
            payload["include_parent"] = include_parent
        return post_json(
            f"{self.base_url.rstrip('/')}/v1/retrieve",
            payload,
            {"X-Service-Token": self.token},
            timeout=self.timeout,
        )


@dataclass(frozen=True)
class ChatClient:
    base_url: str
    api_key: str
    model: str
    timeout: float = 90.0
    cache: ResponseCache | None = None

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int,
        model: str | None = None,
        json_mode: bool = False,
    ) -> str:
        resolved_model = model or self.model
        key = cache_key(
            "chat",
            resolved_model,
            system,
            user,
            str(temperature),
            str(max_tokens),
            str(json_mode),
        )
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        payload: dict[str, Any] = {
            "model": resolved_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        content = ""
        for attempt in range(MAX_CHAT_ATTEMPTS):
            response = post_json(
                f"{self.base_url.rstrip('/')}/chat/completions",
                payload,
                {"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            try:
                content = _extract_content(response)
            except HttpError:
                if attempt < MAX_CHAT_ATTEMPTS - 1:
                    time.sleep(1)
                    continue
                raise
            break
        if self.cache is not None:
            self.cache.put(key, content)
        return content


def _extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HttpError("chat response has no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise HttpError("chat response choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise HttpError("chat response has no message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HttpError("chat response content is empty")
    return content


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise JsonParseError("model response does not contain a JSON object")
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as error:
        raise JsonParseError("model response contains invalid JSON") from error
    if not isinstance(parsed, dict):
        raise JsonParseError("model response JSON is not an object")
    return parsed
