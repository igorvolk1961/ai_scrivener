from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
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
    candidate_k: int
    group_by_source: bool
    group_size: int
    hybrid_enabled: bool
    rerank_enabled: bool
    rerank_model: str
    rerank_batch_size: int
    rerank_candidate_limit: int
    rerank_timeout_seconds: float
    sparse_model: str
    sparse_language: str
    sparse_avg_len: float
    include_parent: bool
    context_max_tokens: int
    parent_chunk_limit: int
    query_max_chars: int
    hnsw_ef: int
    chunk_target_tokens: int
    chunk_max_tokens: int
    chunk_min_tokens: int
    chunk_overlap_sentences: int
    index_batch_size: int
    documents_file_max_mb: int = 50
    documents_upload_timeout_seconds: float = 120.0
    documents_allowed_mime: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/html",
            "text/plain",
            "text/markdown",
        ]
    )
    documents_index_batch_size: int = 64
    documents_cleanup_retention_days: int = 90
    documents_scope_enabled: bool = True


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
    qdrant_documents_collection: str | None = None
    qdrant_api_key: SecretStr | None = None
    embedding_provider: str = "cloudru"
    foundation_api_url: str = "https://foundation-models.api.cloud.ru"
    foundation_api_key: SecretStr | None = None
    foundation_embedding_model: str = "ai-sage/Giga-Embeddings-instruct-480M"
    foundation_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    corpus_dir: Path = Path("/corpus")
    corpus_manifest: Path = Path("/corpus/manifests/2026-11-04.jsonl")
    pdf_cache_dir: Path = Path("/app/.cache/pdf")
    pdf_conversion_timeout_seconds: float = 120.0
    pdf_view_token_ttl_seconds: int = 300
    pdf_public_base_url: str = "http://127.0.0.1:8080"
    rerank_provider: str = "cloudru"
    gigachat_oauth_url: str | None = None
    gigachat_api_url: str | None = None
    gigachat_client_id: str | None = None
    gigachat_client_secret: SecretStr | None = None
    gigachat_scope: str | None = None
    gigachat_model: str | None = None
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
        target = rag.get("chunk_target_tokens")
        maximum = rag.get("chunk_max_tokens")
        minimum = rag.get("chunk_min_tokens")
        if isinstance(target, int) and isinstance(maximum, int) and target > maximum:
            errors.append("rag.chunk_target_tokens must not exceed rag.chunk_max_tokens")
        if isinstance(minimum, int) and isinstance(target, int) and minimum > target:
            errors.append("rag.chunk_min_tokens must not exceed rag.chunk_target_tokens")
        candidate_k = rag.get("candidate_k")
        top_k = rag.get("top_k")
        if isinstance(candidate_k, int) and isinstance(top_k, int) and candidate_k < top_k:
            errors.append("rag.candidate_k must be greater than or equal to rag.top_k")
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
        return ServiceSettings()  # type: ignore[call-arg]
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error


def read_raw_parameters(path: Path | None = None) -> dict[str, Any]:
    config_path = path or Path(os.environ.get("AI_SCRIVENER_CONFIG", str(DEFAULT_CONFIG_PATH)))
    data = _load_yaml(config_path)
    if not isinstance(data, dict):
        raise ConfigurationError("parameters file must contain a mapping")
    return cast(dict[str, Any], data)
