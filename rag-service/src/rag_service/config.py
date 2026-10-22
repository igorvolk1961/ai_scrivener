from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config/parameters.yaml"
DEFAULT_SCHEMA_PATH = REPOSITORY_ROOT / "config/parameters.schema.json"


class ConfigurationError(ValueError):
    pass


class ServiceParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: int
    workers: int
    graceful_shutdown_seconds: int


class HttpParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: list[float]
    retry_status_codes: list[int]


class PlaceholderParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_depth: int
    max_requests_per_task: int
    max_parallel_per_task: int


class LlmParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: list[float]
    temperature_structured: float
    temperature_text: float
    max_output_tokens: int


class RagParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int
    timeout_seconds: float
    embedding_batch_size: int
    embedding_dimension: int | None
    chunk_size_chars: int
    chunk_overlap_chars: int
    index_sync_interval_minutes: int
    search_min_score: float


class GigaChatParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_refresh_skew_seconds: int
    request_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: list[float]


class SchedulerParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orchestration_interval_seconds: int
    waiting_list_interval_seconds: int
    deadline_check_interval_seconds: int
    timer_interval_seconds: int
    batch_size: int
    lock_timeout_seconds: int
    stale_task_seconds: int


class UiParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response_time_seconds: float
    refresh_seconds: int
    page_size: int


class ApplicationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    service: ServiceParameters
    http: HttpParameters
    placeholder_resolution: PlaceholderParameters
    llm: LlmParameters
    rag: RagParameters
    gigachat: GigaChatParameters
    scheduler: SchedulerParameters
    ui: UiParameters


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_token: SecretStr
    qdrant_url: str
    qdrant_collection: str
    qdrant_api_key: SecretStr | None = None
    gigachat_oauth_url: str
    gigachat_api_url: str
    gigachat_client_id: str
    gigachat_client_secret: SecretStr
    gigachat_scope: str
    gigachat_model: str
    gigachat_ca_bundle: str | None = None


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _cross_field_errors(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rag = data.get("rag")
    if isinstance(rag, dict):
        size = rag.get("chunk_size_chars")
        overlap = rag.get("chunk_overlap_chars")
        if isinstance(size, int) and isinstance(overlap, int) and overlap >= size:
            errors.append("rag.chunk_overlap_chars must be less than rag.chunk_size_chars")
    for section_name in ("http", "llm", "gigachat"):
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        retries = section.get("max_retries")
        backoff = section.get("retry_backoff_seconds")
        if isinstance(retries, int) and isinstance(backoff, list) and len(backoff) < retries:
            errors.append(
                f"{section_name}.retry_backoff_seconds must contain at least "
                f"{section_name}.max_retries values"
            )
    return errors


def validate_parameters(data: Any, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    if not isinstance(data, dict):
        raise ConfigurationError("parameters file must contain a mapping")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.path))
    details = [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}" for error in errors
    ]
    details.extend(_cross_field_errors(cast(dict[str, Any], data)))
    if details:
        raise ConfigurationError("; ".join(details))


def load_parameters(path: Path | None = None) -> ApplicationParameters:
    config_path = path or Path(os.environ.get("AI_SCRIVENER_CONFIG", str(DEFAULT_CONFIG_PATH)))
    data = _load_yaml(config_path)
    validate_parameters(data)
    try:
        return ApplicationParameters.model_validate(data)
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error


def load_settings() -> ServiceSettings:
    try:
        return ServiceSettings()
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error


def read_raw_parameters(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(os.environ.get("AI_SCRIVENER_CONFIG", str(DEFAULT_CONFIG_PATH)))
    data = _load_yaml(config_path)
    if not isinstance(data, dict):
        raise ConfigurationError("parameters file must contain a mapping")
    return cast(dict[str, Any], data)
