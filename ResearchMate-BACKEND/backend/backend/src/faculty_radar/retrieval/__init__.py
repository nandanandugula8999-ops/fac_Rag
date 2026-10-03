"""Retrieval: lexical, semantic, and hybrid.

Stage 8 implements exact lexical candidate generation with BM25. BM25 is
deliberately literal: rare technical terms, acronyms, method names, and dataset
phrases match on tokens, not on embedding proximity.

Stage 9 adds vector-space candidates and fuses both ranked lists with
reciprocal-rank fusion. Fused hits preserve both component scores and signal
names, so later stages can distinguish literal matches from vector matches.
"""

from faculty_radar.retrieval.bm25 import BM25Index, KeywordRetriever, keyword_search
from faculty_radar.retrieval.filters import SearchFilters, apply_filters
from faculty_radar.retrieval.hybrid import HybridRetriever, fuse_rankings
from faculty_radar.retrieval.semantic import SemanticRetriever

__all__ = [
    "BM25Index",
    "HybridRetriever",
    "KeywordRetriever",
    "SearchFilters",
    "SemanticRetriever",
    "apply_filters",
    "fuse_rankings",
    "keyword_search",
]
