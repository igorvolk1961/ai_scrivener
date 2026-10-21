from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


class DuplicateKeyError(ValueError):
    pass


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise DuplicateKeyError(f"duplicate key: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=UniqueKeyLoader)


def _format_path(path: Sequence[str | int]) -> str:
    if not path:
        return "$"
    return "$." + ".".join(str(item) for item in path)


def _cross_field_errors(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rag = config.get("rag")
    if isinstance(rag, dict):
        chunk_size = rag.get("chunk_size_chars")
        overlap = rag.get("chunk_overlap_chars")
        if isinstance(chunk_size, int) and isinstance(overlap, int) and overlap >= chunk_size:
            errors.append("$.rag.chunk_overlap_chars must be less than $.rag.chunk_size_chars")
    for section_name in ("http", "llm", "gigachat"):
        section = config.get(section_name)
        if not isinstance(section, dict):
            continue
        retries = section.get("max_retries")
        backoff = section.get("retry_backoff_seconds")
        if isinstance(retries, int) and isinstance(backoff, list) and len(backoff) < retries:
            errors.append(
                f"$.{section_name}.retry_backoff_seconds must contain at least "
                f"$.{section_name}.max_retries values"
            )
    placeholder = config.get("placeholder_resolution")
    if isinstance(placeholder, dict):
        parallel = placeholder.get("max_parallel_per_task")
        if isinstance(parallel, int) and parallel < 1:
            errors.append("$.placeholder_resolution.max_parallel_per_task must be at least 1")
    return errors


def validate_config(root: Path) -> list[str]:
    schema_path = root / "config/parameters.schema.json"
    config_path = root / "config/parameters.yaml"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        return [f"invalid JSON schema: {error.message}"]
    config = _load_yaml(config_path)
    if not isinstance(config, dict):
        return ["config/parameters.yaml must be a mapping"]
    validator = Draft202012Validator(schema)
    errors = [
        f"{_format_path(list(error.absolute_path))}: {error.message}"
        for error in sorted(validator.iter_errors(config), key=lambda item: list(item.path))
    ]
    errors.extend(_cross_field_errors(cast(dict[str, Any], config)))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate config/parameters.yaml")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    try:
        errors = validate_config(root)
    except (OSError, ValueError, json.JSONDecodeError, DuplicateKeyError, yaml.YAMLError) as error:
        print(f"config validation failed: {error}", file=sys.stderr)
        return 1
    if errors:
        for message in errors:
            print(f"config validation failed: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
