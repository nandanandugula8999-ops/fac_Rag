"""Evaluation harness.

Stage 16 of the pipeline. Scores retrieval strategies against human-graded
benchmarks and reports exactly what was measured - nothing more.

The central honesty rule: metrics are computed only over human-graded queries.
Ungraded queries are excluded, never scored against assumed relevance. When
fewer than `min_graded_items` queries are graded, the whole report is marked
ungraded rather than presenting small-sample noise as a score. Fields the
harness cannot measure from ranked outputs (citation correctness, resolution
accuracy) stay `None` with a note saying so, instead of being filled with
convenient zeros.
"""

from faculty_radar.evaluation.metrics import (
    RetrievalMetricsComputer,
    average_metrics,
    score_case,
)
from faculty_radar.evaluation.suite import EvaluationRunner, evaluate_strategy

__all__ = [
    "EvaluationRunner",
    "RetrievalMetricsComputer",
    "average_metrics",
    "evaluate_strategy",
    "score_case",
]
