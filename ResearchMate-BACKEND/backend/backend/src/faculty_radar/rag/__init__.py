"""Retrieval-augmented generation.

Stage 15b of the pipeline. Assembles the grounded context for an answer:

  * expertise search produces ranked, explained faculty matches
  * evidence selection narrows those matches to budgeted citable passages
  * context assembly fits the passages into a bounded context, dropping whole
    items that do not fit - quotes are never truncated, because a truncated
    quote would fail verification
  * the LLM boundary drafts an answer strictly from that context
  * verification checks every claim before the answer is returned

RAG is the last stage, not the architecture. It must never be the sole source
of a claim that the evidence layer can support on its own.
"""

from faculty_radar.rag.pipeline import RagPipeline, answer_query

__all__ = [
    "RagPipeline",
    "answer_query",
]
