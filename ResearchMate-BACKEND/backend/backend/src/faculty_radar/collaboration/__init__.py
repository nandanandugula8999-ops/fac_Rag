"""Collaboration discovery engine.

Stage 12 of the pipeline. Finds who already works together and who should.

The two collaboration types are evidence-graded, not vibe-graded:

* EXISTING  - the pair shares at least `min_coauthored_works` authored works.
  Authorship is observed, so this is the strongest claim the system makes.
* POTENTIAL - the pair shares no works but publishes on overlapping topics that
  are adjacent without being near-duplicates. Topic overlap is a hypothesis
  about complementarity, and it is labeled as one: never presented as an
  existing relationship.

Everything structural comes from the knowledge graph (`collaborated_with`
edges, shared works, per-person topics). The engine never compares names or
free text to decide that two people collaborate.
"""

from faculty_radar.collaboration.engine import CollaborationEngine, find_collaborations

__all__ = [
    "CollaborationEngine",
    "find_collaborations",
]
