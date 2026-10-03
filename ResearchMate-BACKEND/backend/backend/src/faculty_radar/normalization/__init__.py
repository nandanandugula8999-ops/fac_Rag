"""Cleaning and normalization.

Stage 2 of the pipeline. Converts raw snapshots in `paths.raw` into canonical
records in `paths.interim`.

Responsibilities:
  * strip diacritics, unify whitespace, lowercase for comparison keys
  * parse dates, expand abbreviations, normalize DOIs / ORCID / ROR IDs
  * standardize concept and topic vocabularies across sources
  * deduplicate trivially repeated records

Must not: infer authorship, merge identities, or drop fields that a later stage
may need. Normalization must be reversible from `raw/`.

Submodules:
  text      - deterministic string canonicalization and tokenization
  abstract  - OpenAlex `abstract_inverted_index` reconstruction
  authors   - raw author payload -> NormalizedAuthor
  works     - raw work payload -> NormalizedWork
  pipeline  - orchestration: raw store -> interim store
"""

from faculty_radar.normalization.abstract import reconstruct_abstract
from faculty_radar.normalization.authors import normalize_author
from faculty_radar.normalization.pipeline import NormalizationResult, normalize_all
from faculty_radar.normalization.text import (
    canonical_key,
    extract_orcid,
    normalize_doi,
    normalize_ror,
    strip_accents,
    tokenize,
)
from faculty_radar.normalization.works import normalize_work

__all__ = [
    "NormalizationResult",
    "canonical_key",
    "extract_orcid",
    "normalize_all",
    "normalize_author",
    "normalize_doi",
    "normalize_ror",
    "normalize_work",
    "reconstruct_abstract",
    "strip_accents",
    "tokenize",
]
