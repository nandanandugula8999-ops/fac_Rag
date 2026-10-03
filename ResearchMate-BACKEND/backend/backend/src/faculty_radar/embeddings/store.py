"""Vector index persistence and cosine search.

Vectors live in a NumPy `.npz` matrix while document IDs, text hashes, and the
embedding model/version live beside them in JSON. The two files are written
atomically and always checked together: a vector is never trusted without the
metadata identifying the representation that produced it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from faculty_radar.config import get_logger
from faculty_radar.models import CorpusDocument
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


class VectorIndexError(RuntimeError):
    """Stored vectors are missing, corrupt, or incompatible."""


@dataclass(frozen=True)
class VectorHit:
    doc_id: str
    score: float


@dataclass(frozen=True)
class VectorIndex:
    doc_ids: tuple[str, ...]
    vectors: np.ndarray
    embedding_model: str
    embedding_version: str
    text_hashes: dict[str, str]
    exists: bool = True

    def __len__(self) -> int:
        return len(self.doc_ids)

    @property
    def dimension(self) -> int:
        return int(self.vectors.shape[1]) if self.vectors.ndim == 2 else 0

    def vectors_by_id(self) -> dict[str, np.ndarray]:
        return {doc_id: self.vectors[i] for i, doc_id in enumerate(self.doc_ids)}

    def vector_for(self, doc_id: str) -> np.ndarray:
        try:
            position = self.doc_ids.index(doc_id)
        except ValueError as exc:
            raise VectorIndexError(f"document {doc_id!r} is not in the vector index") from exc
        return self.vectors[position]

    def ensure_compatible(
        self, *, embedding_model: str, embedding_version: str, dimension: int
    ) -> None:
        """Refuse to use vectors from another representation."""
        problems = []
        if self.embedding_model != embedding_model:
            problems.append(f"model {self.embedding_model!r} != {embedding_model!r}")
        if self.embedding_version != embedding_version:
            problems.append(f"version {self.embedding_version!r} != {embedding_version!r}")
        if self.dimension != dimension:
            problems.append(f"dimension {self.dimension} != {dimension}")
        if problems:
            raise VectorIndexError(
                "stale vector index; rebuild it instead of mixing representations: "
                + "; ".join(problems)
            )

    def needs_rebuild(self, documents: list[CorpusDocument]) -> bool:
        """Whether stored vectors no longer match these documents."""
        from faculty_radar.embeddings.backends import text_hash

        if {doc.doc_id for doc in documents} != set(self.doc_ids):
            return True
        return any(
            self.text_hashes.get(doc.doc_id) != text_hash(doc.embed_text) for doc in documents
        )

    def search(self, query: np.ndarray, *, top_k: int = 10) -> list[VectorHit]:
        """Cosine search over L2-normalized index vectors."""
        if top_k <= 0 or len(self) == 0:
            return []
        if query.shape != (self.dimension,):
            raise VectorIndexError(
                f"query dimension {query.shape} does not match index {self.dimension}"
            )
        if not np.any(query):
            return []

        scores = self.vectors.astype(np.float64) @ query.astype(np.float64)
        ranked = sorted(
            range(len(self)),
            key=lambda i: (-float(scores[i]), self.doc_ids[i]),
        )
        return [VectorHit(doc_id=self.doc_ids[i], score=float(scores[i])) for i in ranked[:top_k]]


def _safe_model_name(model: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in model).strip("_")
    return safe or "model"


class VectorStore:
    """Reads and writes one model-namespaced vector index."""

    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = paths or build_paths()

    def index_paths(self, embedding_model: str) -> tuple[Path, Path]:
        name = _safe_model_name(embedding_model)
        return (self.paths.vectors / f"{name}.npz", self.paths.vectors / f"{name}.json")

    def write_index(
        self,
        documents: list[CorpusDocument],
        vectors: list[np.ndarray],
        *,
        embedding_model: str,
        embedding_version: str,
    ) -> Path:
        """Persist vectors and their identifying metadata together."""
        from faculty_radar.embeddings.backends import text_hash

        if not documents:
            raise VectorIndexError("refusing to write an empty vector index")
        if len(documents) != len(vectors):
            raise VectorIndexError(
                f"{len(documents)} documents but {len(vectors)} vectors; refusing to misalign them"
            )
        if len({doc.doc_id for doc in documents}) != len(documents):
            raise VectorIndexError("duplicate document IDs cannot share one vector index")

        dimension = int(np.asarray(vectors[0]).shape[0])
        matrix_rows = []
        for doc_id, vector in zip([doc.doc_id for doc in documents], vectors, strict=True):
            row = np.asarray(vector, dtype=np.float32).reshape(-1)
            if row.shape != (dimension,):
                raise VectorIndexError(
                    f"document {doc_id!r} has shape {row.shape}, expected ({dimension},)"
                )
            matrix_rows.append(row)
        matrix = np.stack(matrix_rows).astype(np.float32, copy=False)

        metadata = {
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
            "dimension": dimension,
            "document_count": len(documents),
            "documents": [
                {"doc_id": doc.doc_id, "text_hash": text_hash(doc.embed_text)} for doc in documents
            ],
        }

        self.paths.ensure()
        index_path, metadata_path = self.index_paths(embedding_model)
        self._atomic_write_npz(index_path, matrix)
        self._atomic_write_json(metadata_path, metadata)
        logger.info(
            "vector index written",
            extra={
                "path": str(index_path),
                "documents": len(documents),
                "dimension": dimension,
                "embedding_model": embedding_model,
            },
        )
        return index_path

    def load_index(self, embedding_model: str, embedding_version: str) -> VectorIndex:
        """Load a stored index, or an explicitly marked absent index."""
        index_path, metadata_path = self.index_paths(embedding_model)
        if not index_path.exists() or not metadata_path.exists():
            logger.warning(
                "no vector index found; returning an absent index",
                extra={"path": str(index_path)},
            )
            return VectorIndex(
                doc_ids=(),
                vectors=np.zeros((0, 0), dtype=np.float32),
                embedding_model=embedding_model,
                embedding_version=embedding_version,
                text_hashes={},
                exists=False,
            )

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VectorIndexError(f"vector metadata {metadata_path} is unreadable") from exc
        try:
            with np.load(index_path) as archive:
                matrix = np.asarray(archive["vectors"], dtype=np.float32)
        except (OSError, ValueError, KeyError) as exc:
            raise VectorIndexError(f"vector matrix {index_path} is unreadable") from exc

        entries = metadata.get("documents", [])
        doc_ids = tuple(entry["doc_id"] for entry in entries)
        if matrix.ndim != 2 or matrix.shape[0] != len(doc_ids):
            raise VectorIndexError(
                f"vector matrix shape {matrix.shape} does not match {len(doc_ids)} metadata rows"
            )
        if metadata.get("dimension") != int(matrix.shape[1]):
            raise VectorIndexError("vector metadata dimension does not match stored matrix")

        return VectorIndex(
            doc_ids=doc_ids,
            vectors=matrix,
            embedding_model=metadata.get("embedding_model", embedding_model),
            embedding_version=metadata.get("embedding_version", embedding_version),
            text_hashes={entry["doc_id"]: entry["text_hash"] for entry in entries},
            exists=True,
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def _atomic_write_npz(path: Path, matrix: np.ndarray) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        # Pass an open handle: np.savez appends `.npz` to a bare path, which
        # would defeat the atomic temporary-file dance.
        with tmp.open("wb") as handle:
            np.savez(handle, vectors=matrix)
        tmp.replace(path)
        return path
