"""Data ingestion from external research sources.

Stage 1 of the pipeline. Pulls raw records from OpenAlex and institutional
endpoints, applies rate limiting and retries, and writes byte-faithful
snapshots to `paths.raw`.

Design rules for this package:
  * never mutate or overwrite anything in `raw/` - append-only snapshots
  * record the fetch timestamp and request URL alongside every payload so
    ingestion is reproducible and citable
  * no cleaning, no deduplication of *content*, no interpretation

Submodules:
  client   - HTTP access, cursor pagination, retry/backoff, rate limiting
  cache    - on-disk response cache keyed by request, TTL-expiring
  store    - append-only JSON Lines snapshot store
  pipeline - orchestration: institution -> authors -> works
"""

from faculty_radar.ingestion.cache import ResponseCache, make_cache_key
from faculty_radar.ingestion.client import OpenAlexClient, OpenAlexError
from faculty_radar.ingestion.pipeline import IngestionResult, ingest_all, ingest_institution
from faculty_radar.ingestion.store import ENTITIES, RawStore

__all__ = [
    "ENTITIES",
    "IngestionResult",
    "OpenAlexClient",
    "OpenAlexError",
    "RawStore",
    "ResponseCache",
    "ingest_all",
    "ingest_institution",
    "make_cache_key",
]
