"""Expertise engine.

Stage 11 of the pipeline. Answers "who knows about this topic?" and is the
component that separates what the system can honestly claim from what it
cannot.

Two distinct kinds of match, never conflated:
  * STATED   - the faculty member or their institution explicitly declared this
               topic, e.g. on a consented profile or project description
  * INFERRED - the topic was derived from publication content similarity

Every returned faculty record carries both the aggregate score and the
per-signal breakdown, so a user can always see which of the two produced a
result. Scores are normalized 0-1 and always accompanied by at least one
supporting passage.
"""

from faculty_radar.expertise.engine import ExpertiseEngine, find_experts

__all__ = [
    "ExpertiseEngine",
    "find_experts",
]
