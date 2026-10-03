"""Build a production search corpus in the data lake from live OpenAlex.

Runs the REAL pipeline stages end to end, with artifacts in data/:

    ingest (live OpenAlex) -> data/raw/
    normalize              -> data/interim/ (authors.jsonl, works.jsonl)
    resolve                -> data/processed/ (researchers.jsonl, decisions, review queue)
    consent (demo)         -> data/processed/consent.json
    link                   -> data/processed/faculty.jsonl
    corpus                 -> data/corpus/documents.jsonl
    vectors                -> data/vectors/hashing_v1.{npz,json}
    bm25                   rebuilt in memory and probe-queried (no disk format:
                           derived data, rebuilt deterministically at startup)

Scope: one institution (default: Santa Fe Institute, I1308548392 - 355
authors, interdisciplinary). Override with --institution. Caps come from
settings (FR_INGESTION__MAX_AUTHORS etc.); defaults capture SFI completely.

CONSENT WARNING: this script writes a demo consent registry covering every
resolved in-scope researcher, with NO stated topics. That is a demo-only
assumption so arbitrary-topic search works out of the box. A real deployment
MUST replace data/processed/consent.json with a curated human registry and
re-run linking + corpus. Because no stated topics exist, all demo expertise
is honestly labeled EVIDENCE_BASED or INFERRED - never STATED.

Usage (repo root):
    $env:PYTHONPATH = "src"
    .\\.venv\\Scripts\\python.exe scripts\\build_lake.py --institution I1308548392
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from faculty_radar.config import get_logger, get_settings  # noqa: E402
from faculty_radar.corpus.builder import build_corpus  # noqa: E402
from faculty_radar.embeddings.pipeline import build_embeddings  # noqa: E402
from faculty_radar.ingestion.client import OpenAlexClient  # noqa: E402
from faculty_radar.ingestion.pipeline import ingest_institution  # noqa: E402
from faculty_radar.ingestion.store import RawStore  # noqa: E402
from faculty_radar.linking.builder import link_faculty  # noqa: E402
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry, registry_path  # noqa: E402
from faculty_radar.normalization.pipeline import InterimStore, normalize_all  # noqa: E402
from faculty_radar.paths import build_paths  # noqa: E402
from faculty_radar.resolution.resolver import resolve_researchers  # noqa: E402
from faculty_radar.retrieval.bm25 import KeywordRetriever  # noqa: E402

logger = get_logger(__name__)

DEFAULT_INSTITUTION = "I1308548392"  # Santa Fe Institute


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the search corpus data lake.")
    parser.add_argument("--institution", default=DEFAULT_INSTITUTION)
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--max-authors", type=int, default=60)
    parser.add_argument("--max-works-per-author", type=int, default=25)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    settings = settings.model_copy(
        update={
            "ingestion": settings.ingestion.model_copy(
                update={
                    "max_authors": args.max_authors,
                    "max_works_per_author": args.max_works_per_author,
                }
            )
        }
    )
    paths = build_paths(settings)
    report: dict = {"institution": args.institution}

    # 1. Ingest live OpenAlex into data/raw/.
    client = OpenAlexClient(settings.openalex)
    raw = RawStore(paths)
    ingestion = ingest_institution(client, raw, args.institution, settings.ingestion)
    client.close()
    report["ingestion"] = ingestion.as_dict()
    print(
        f"[1/7] ingest: {ingestion.authors_stored} authors, "
        f"{ingestion.works_stored} works stored ({ingestion.requests} requests)"
    )

    # 2. Normalize into data/interim/.
    normalize_all(raw, settings, paths)
    interim = InterimStore(paths)
    authors = interim.load_authors()
    works = interim.load_works()
    report["normalized"] = {"authors": len(authors), "works": len(works)}
    print(f"[2/7] normalize: {len(authors)} authors, {len(works)} works")

    # 3. Resolve identities (homonyms stay separate by construction).
    resolved = resolve_researchers(authors, works, settings, paths, store=True)
    report["resolution"] = {
        "researchers": len(resolved.researchers),
        "needs_review": len(resolved.needs_review),
    }
    print(
        f"[3/7] resolve: {len(resolved.researchers)} researchers, "
        f"{len(resolved.needs_review)} need review"
    )

    # 4. Demo consent registry: every resolved in-scope researcher, no stated
    #    topics. See module docstring for why this is demo-only.
    registry = ConsentRegistry(
        {
            researcher.researcher_id: ConsentEntry(
                researcher_id=researcher.researcher_id,
                consented=True,
                reviewed_by=(
                    "demo-build: in-scope assumed consented; replace with "
                    "curated registry in production"
                ),
                consented_at=date.today().isoformat(),
            )
            for researcher in resolved.researchers
        },
        enforce=True,
    )
    consent_path = registry.write(registry_path(settings, paths))
    profiles = link_faculty(
        resolved.researchers,
        authors,
        works,
        settings,
        paths,
        consent=registry,
        store=True,
    )
    report["linking"] = {
        "consent_registry": str(consent_path),
        "consented_profiles": len(profiles),
    }
    print(f"[4/7] link: {len(profiles)} consented profiles")

    # 5. Corpus chunks.
    documents = build_corpus(profiles, works, settings, paths, store=True)
    report["corpus"] = {"documents": len(documents)}
    print(f"[5/7] corpus: {len(documents)} documents")

    # 6. Persisted vector index.
    embedding = build_embeddings(documents, settings, paths, store=True)
    report["vectors"] = {
        "path": str(embedding.path),
        "dimension": embedding.stats["dimension"],
        "model": embedding.stats["embedding_model"],
    }
    print(
        f"[6/7] vectors: {embedding.stats['documents']} vectors "
        f"({embedding.stats['reused']} reused, {embedding.stats['computed']} computed)"
    )

    # 7. BM25 index rebuilt over the full corpus + probe queries.
    retriever = KeywordRetriever(documents, settings)
    probes = {
        name: [hit.document.work_id for hit in retriever.search(name, top_k=3)]
        for name in ("network science", "quantum")
    }
    report["bm25"] = {
        "indexed_documents": len(documents),
        "probe_hits": probes,
    }
    print(f"[7/7] bm25: {len(documents)} documents indexed; probes ok")

    print(json.dumps(report, indent=2, default=str))
    (Path(args.data_dir) / "lake_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
