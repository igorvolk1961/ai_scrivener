from __future__ import annotations

import pytest

from rag_service.config import (
    ConfigurationError,
    load_parameters,
    read_raw_parameters,
    validate_parameters,
)


def test_repository_parameters_are_loaded() -> None:
    parameters = load_parameters()
    assert parameters.version == 1
    assert parameters.rag.top_k > 0
    assert parameters.rag.chunk_overlap_chars < parameters.rag.chunk_size_chars
    assert parameters.service.port > 0


def test_invalid_cross_field_values_are_rejected() -> None:
    data = read_raw_parameters()
    rag = data["rag"]
    assert isinstance(rag, dict)
    rag["chunk_overlap_chars"] = rag["chunk_size_chars"]
    with pytest.raises(ConfigurationError):
        validate_parameters(data)


def test_missing_required_section_is_rejected() -> None:
    data = read_raw_parameters()
    del data["rag"]
    with pytest.raises(ConfigurationError):
        validate_parameters(data)
