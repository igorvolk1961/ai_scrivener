from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest
from docx import Document

from rag_service.corpus import CorpusFile
from rag_service.pdf_conversion import PdfConverter
from rag_service.view_tokens import create_view_token, verify_view_token


def test_docx_converted_to_cached_pdf(tmp_path: Path) -> None:
    if shutil.which("soffice") is None:
        pytest.skip("LibreOffice is not installed")
    source = tmp_path / "sample.docx"
    document = Document()
    document.add_heading("Проверка DOCX", level=1)
    document.add_paragraph("Текст для конвертации в PDF.")
    document.save(source)

    corpus_file = CorpusFile(
        path=source,
        original_name="sample.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    converter = PdfConverter(tmp_path / "cache", timeout_seconds=60)

    result = asyncio.run(converter.to_pdf("sample-source", corpus_file))
    assert result.is_file()
    assert result.read_bytes().startswith(b"%PDF")
    cached_result = asyncio.run(converter.to_pdf("sample-source", corpus_file))
    assert cached_result == result


def test_pdf_is_returned_as_is(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    corpus_file = CorpusFile(path=source, original_name="sample.pdf", mime="application/pdf")
    converter = PdfConverter(tmp_path / "cache")

    assert asyncio.run(converter.to_pdf("pdf-source", corpus_file)) == source


def test_view_token_round_trip() -> None:
    token = create_view_token("secret", "source-id", 60)
    assert verify_view_token("secret", "source-id", token)
    assert not verify_view_token("secret", "other-source", token)
    assert not verify_view_token("wrong", "source-id", token)


def test_view_token_rejects_expired() -> None:
    token = create_view_token("secret", "source-id", -1)
    assert not verify_view_token("secret", "source-id", token)
