"""Research trend engine.

Stage 13 of the pipeline. Measures which topics are rising, declining, stable,
or emerging by comparing per-year publication rates across a recent window and
a baseline window.

Small-number noise is the enemy here, so two gates apply before any direction
is claimed: a topic needs at least `min_publications` total works to be
reported at all, and a rising/emerging call needs at least
`min_recent_publications` in the recent window. A topic absent from the
baseline with real recent volume is "emerging", not infinitely growing - the
growth ratio is reported as the recent volume itself rather than a division by
zero dressed up as insight.

Undated works are excluded from window math and counted in the report notes,
because a trend built on unknown timestamps would be a guess with decimals.
"""

from faculty_radar.trends.engine import TrendEngine, analyze_trends

__all__ = [
    "TrendEngine",
    "analyze_trends",
]
