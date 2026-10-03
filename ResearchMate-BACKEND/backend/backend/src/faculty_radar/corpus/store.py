"""Research corpus persistence.

Writes to `data/corpus/`:

  documents.jsonl  one corpus document per line, ordered by document ID
  corpus.json      the same documents plus build counts

Writes go through a temporary file and an atomic replace so a crashed run
cannot leave a half-written corpus behind.
"""

from __future__ import annotations

import json
from pathlib import Path

from faculty_radar.config import get_logger
from faculty_radar.models import CorpusDocument
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)

DEFAULT_DOCUMENTS_NAME = "documents.jsonl"
DEFAULT_CATALOG_NAME = "corpus.json"


class CorpusStore:
    """Reads and writes corpus documents."""

    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = paths or build_paths()

    @property
    def documents_path(self) -> Path:
        return self.paths.corpus / DEFAULT_DOCUMENTS_NAME

    @property
    def catalog_path(self) -> Path:
        return self.paths.corpus / DEFAULT_CATALOG_NAME

    def write_documents(self, documents: list[CorpusDocument]) -> Path:
        """Persist documents in stable document-ID order."""
        from faculty_radar.corpus.builder import corpus_stats

        self.paths.ensure()
        ordered = sorted(documents, key=lambda doc: doc.doc_id)
        records = [doc.model_dump(mode="json") for doc in ordered]
        payload = {"meta": corpus_stats(ordered), "documents": records}

        self._atomic_write_json(self.catalog_path, payload)
        self._atomic_write_jsonl(self.documents_path, records)
        logger.info(
            "research corpus written",
            extra={"path": str(self.documents_path), **payload["meta"]},
        )
        return self.documents_path

    def load_documents(self) -> list[CorpusDocument]:
        """Load documents, skipping malformed lines without failing the run."""
        if not self.documents_path.exists():
            logger.warning(
                "no research corpus found; returning no documents",
                extra={"path": str(self.documents_path)},
            )
            return []

        documents: list[CorpusDocument] = []
        with self.documents_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    documents.append(CorpusDocument.model_validate(json.loads(line)))
                except (json.JSONDecodeError, ValueError):
                    continue
        return sorted(documents, key=lambda doc: doc.doc_id)

    def load_catalog(self) -> dict:
        """Load corpus metadata and documents, or an empty catalog."""
        if not self.catalog_path.exists():
            return {}
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def _atomic_write_jsonl(path: Path, records: list[dict]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        tmp.replace(path)
        return path
