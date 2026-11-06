from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusFile:
    path: Path
    original_name: str
    mime: str


class CorpusResolver:
    def __init__(self, manifest_path: Path, corpus_dir: Path) -> None:
        self._manifest_path = manifest_path
        self._corpus_dir = corpus_dir
        self._records: dict[str, dict[str, object]] | None = None

    def _load(self) -> dict[str, dict[str, object]]:
        if self._records is None:
            records: dict[str, dict[str, object]] = {}
            if self._manifest_path.exists():
                with self._manifest_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        payload = json.loads(line)
                        source_id = str(payload.get("sha256", ""))
                        if source_id:
                            records[source_id] = payload
            self._records = records
        return self._records

    def resolve(self, source_id: str) -> CorpusFile | None:
        record = self._load().get(source_id)
        if record is None:
            return None
        relative = str(record.get("stored_path", ""))
        if not relative:
            return None
        root = self._corpus_dir.resolve()
        path = (self._corpus_dir / relative).resolve()
        if root not in path.parents or not path.is_file():
            return None
        return CorpusFile(
            path=path,
            original_name=str(record.get("original_name") or path.name),
            mime=str(record.get("mime") or "application/octet-stream"),
        )
