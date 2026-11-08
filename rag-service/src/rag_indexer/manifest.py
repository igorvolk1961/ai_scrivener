from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class CorpusRecord:
    sha256: str
    stored_path: str
    mime: str
    status: str
    title: str
    doc_type: str = ""
    authority: str = ""
    published_at: str = ""
    source_url: str = ""
    original_name: str = ""
    employee: str = ""
    notes: str = ""
    license: str = ""
    source_kind: str = ""
    size: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return self.published_at or self.sha256

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CorpusRecord:
        sha256 = str(payload.get("sha256", "")).strip()
        stored_path = str(payload.get("stored_path", "")).strip()
        if not sha256 or not stored_path:
            raise ManifestError("manifest record is missing sha256 or stored_path")
        return cls(
            sha256=sha256,
            stored_path=stored_path,
            mime=str(payload.get("mime", "")),
            status=str(payload.get("status", "downloaded")),
            title=str(payload.get("title", "")),
            doc_type=str(payload.get("doc_type", "")),
            authority=str(payload.get("authority", "")),
            published_at=str(payload.get("published_at", "")),
            source_url=str(payload.get("source_url", "")),
            original_name=str(payload.get("original_name", "")),
            employee=str(payload.get("employee", "")),
            notes=str(payload.get("notes", "")),
            license=str(payload.get("license", "")),
            source_kind=str(payload.get("source_kind", "")),
            size=int(payload.get("size", 0) or 0),
            raw=payload,
        )

    def metadata(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "stored_path": self.stored_path,
            "mime": self.mime,
            "status": self.status,
            "doc_type": self.doc_type,
            "authority": self.authority,
            "published_at": self.published_at,
            "source_url": self.source_url,
            "original_name": self.original_name,
            "employee": self.employee,
            "notes": self.notes,
            "license": self.license,
            "source_kind": self.source_kind,
            "size": self.size,
        }


def load_manifest(path: Path) -> list[CorpusRecord]:
    records: list[CorpusRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise ManifestError(f"{path}:{line_number}: invalid JSON") from error
            try:
                records.append(CorpusRecord.from_dict(payload))
            except ManifestError as error:
                raise ManifestError(f"{path}:{line_number}: {error}") from error
    return records


def select_records(
    records: list[CorpusRecord],
    statuses: set[str],
) -> list[CorpusRecord]:
    selected: dict[str, CorpusRecord] = {}
    for record in records:
        selected[record.sha256] = record
    return [record for record in selected.values() if not statuses or record.status in statuses]


def latest_manifest(corpus_dir: Path) -> Path:
    manifests = sorted((corpus_dir / "manifests").glob("*.jsonl"))
    if not manifests:
        raise ManifestError(f"no manifest *.jsonl found in {corpus_dir / 'manifests'}")
    return manifests[-1]
