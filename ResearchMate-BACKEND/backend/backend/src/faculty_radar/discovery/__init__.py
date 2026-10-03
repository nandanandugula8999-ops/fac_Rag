"""Hybrid on-demand research discovery.

Live external sources feed the EXISTING pipeline instead of a pre-downloaded
corpus. Per query: normalize -> discover candidate works from a provider
(OpenAlex by default) -> adapt payloads through the real normalization,
resolution, linking, and corpus stages -> run the unchanged RAG pipeline
(retrieval, rerank, expertise, evidence, generation, verification).

Nothing here retrieves, ranks, or generates. It only finds candidates and
shapes them into the internal format; every downstream stage is reused
verbatim, which is why a discovered answer carries the same guarantees as a
corpus-built one.

Submodules:
  providers  - DiscoveryProvider protocol, OpenAlex + Crossref implementations
  service    - cached discovery plus the payload-to-corpus adapter
"""

from faculty_radar.discovery.providers import (
    DiscoveryProvider,
    OpenAlexDiscoveryProvider,
    normalize_query,
)
from faculty_radar.discovery.service import DiscoveryResult, DiscoveryService

__all__ = [
    "DiscoveryProvider",
    "DiscoveryResult",
    "DiscoveryService",
    "OpenAlexDiscoveryProvider",
    "normalize_query",
]
