"""Evidence selection before generation.

Stage 14 of the pipeline. Narrows expertise matches down to the citable
passages the generator may use - at most `max_items`, with per-faculty and
per-document caps so one prolific researcher cannot crowd out everyone else,
and a relevance floor so weak passages never reach the answer.

Selection only reorders and filters. It never rewrites quotes, merges
passages, or invents evidence: every selected item is byte-identical to the
passage the expertise engine produced.
"""

from faculty_radar.evidence.selection import EvidenceSelector, select_evidence

__all__ = [
    "EvidenceSelector",
    "select_evidence",
]
