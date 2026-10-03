"""Reranking.

Stage 10 of the pipeline. Reorders the hybrid candidate set before it reaches
the expertise engine.

This is a deterministic field-weighted reranker, not a neural cross-encoder:
title, abstract, topic, and keyword matches contribute with configured weights,
so a literal title match outranks a passing abstract mention for the same
query. The hybrid candidate order breaks field-score ties (weighted method) or
is fused with the field ranking (RRF method).

Every reranked hit keeps its original hybrid score, gains a rerank score, and
is paired with a verbatim evidence span from the document text. A reranked hit
can therefore be explained and cited rather than presented as an opaque number.
"""

from faculty_radar.ranking.rerank import RerankResult, rerank_hits

__all__ = [
    "RerankResult",
    "rerank_hits",
]
