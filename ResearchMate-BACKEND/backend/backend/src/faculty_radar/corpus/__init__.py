"""Research corpus construction.

Stage 6 turns consented faculty profiles and normalized publications into
retrievable text units. Two deliberate grain choices:

* one whole-publication chunk for each consented faculty-publication link;
  long-publication window splitting is intentionally deferred;
* one faculty-profile chunk per consented faculty member for declared
  expertise and project descriptions.

Whole-publication chunks are marked derived. Profile chunks are marked stated
only when the consent registry actually declared topics or projects. Field
origins preserve that separation even when identity context accompanies stated
expertise.
"""

from faculty_radar.corpus.builder import CorpusBuilder, build_corpus, corpus_stats
from faculty_radar.corpus.store import CorpusStore

__all__ = [
    "CorpusBuilder",
    "CorpusStore",
    "build_corpus",
    "corpus_stats",
]
