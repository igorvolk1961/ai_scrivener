from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from rag_service.corpus import CorpusFile


class PdfConversionError(RuntimeError):
    pass


class PdfConverter:
    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: float = 120.0,
        executable: str = "soffice",
    ) -> None:
        self._cache_dir = cache_dir
        self._timeout_seconds = timeout_seconds
        self._executable = executable
        self._locks: dict[str, asyncio.Lock] = {}

    async def to_pdf(self, source_id: str, source: CorpusFile) -> Path:
        if source.path.suffix.lower() == ".pdf" or source.mime == "application/pdf":
            return source.path

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
        cached = self._cache_dir / f"{cache_key}.pdf"
        if cached.is_file() and cached.stat().st_size > 0:
            return cached

        lock = self._locks.setdefault(source_id, asyncio.Lock())
        async with lock:
            if cached.is_file() and cached.stat().st_size > 0:
                return cached
            await self._convert(source.path, cached)
        return cached

    async def _convert(self, source: Path, target: Path) -> None:
        with tempfile.TemporaryDirectory(prefix="rag-pdf-", dir=self._cache_dir) as raw_dir:
            work_dir = Path(raw_dir)
            profile_dir = work_dir / "lo-profile"
            command = [
                self._executable,
                "--headless",
                "--norestore",
                "--nolockcheck",
                "--nodefault",
                "--nofirststartwizard",
                f"-env:UserInstallation=file://{profile_dir}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(work_dir),
                str(source),
            ]
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError as error:
                process.kill()
                await process.wait()
                raise PdfConversionError(
                    f"LibreOffice timed out after {self._timeout_seconds:.0f}s"
                ) from error
            if process.returncode != 0:
                details = (stderr or stdout).decode("utf-8", errors="replace").strip()
                raise PdfConversionError(
                    f"LibreOffice exited with code {process.returncode}: {details[:500]}"
                )

            produced = work_dir / f"{source.stem}.pdf"
            if not produced.is_file():
                candidates = sorted(work_dir.glob("*.pdf"))
                if not candidates:
                    raise PdfConversionError("LibreOffice did not produce a PDF file")
                produced = candidates[0]

            os.replace(produced, target)
