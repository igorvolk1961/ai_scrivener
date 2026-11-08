from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class StateError(ValueError):
    pass


@dataclass
class DocumentState:
    status: str
    chunks: int = 0
    title: str = ""
    indexed_at: str = ""
    error: str = ""


@dataclass
class IndexState:
    pipeline_version: str
    documents: dict[str, DocumentState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, pipeline_version: str) -> IndexState:
        if not path.exists():
            return cls(pipeline_version=pipeline_version)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StateError(f"cannot read index state {path}") from error
        if not isinstance(payload, dict):
            raise StateError(f"invalid index state {path}")
        if str(payload.get("pipeline_version", "")) != pipeline_version:
            return cls(pipeline_version=pipeline_version)
        documents: dict[str, DocumentState] = {}
        for sha, data in payload.get("documents", {}).items():
            if not isinstance(data, dict):
                continue
            documents[str(sha)] = DocumentState(
                status=str(data.get("status", "failed")),
                chunks=int(data.get("chunks", 0) or 0),
                title=str(data.get("title", "")),
                indexed_at=str(data.get("indexed_at", "")),
                error=str(data.get("error", "")),
            )
        return cls(pipeline_version=pipeline_version, documents=documents)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pipeline_version": self.pipeline_version,
            "documents": {sha: asdict(document) for sha, document in self.documents.items()},
        }
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)

    def is_indexed(self, sha256: str) -> bool:
        document = self.documents.get(sha256)
        return document is not None and document.status == "indexed"

    def mark_indexed(
        self,
        sha256: str,
        *,
        chunks: int,
        title: str,
        indexed_at: str,
    ) -> None:
        self.documents[sha256] = DocumentState(
            status="indexed",
            chunks=chunks,
            title=title,
            indexed_at=indexed_at,
        )

    def mark_failed(self, sha256: str, error: str) -> None:
        self.documents[sha256] = DocumentState(status="failed", error=error)

    def missing(self, selected_shas: set[str]) -> list[str]:
        return [
            sha
            for sha, document in self.documents.items()
            if document.status == "indexed" and sha not in selected_shas
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "documents": {sha: asdict(document) for sha, document in self.documents.items()},
        }
