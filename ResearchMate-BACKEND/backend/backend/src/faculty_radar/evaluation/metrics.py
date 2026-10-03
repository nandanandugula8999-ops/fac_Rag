"""Graded retrieval metrics: precision, recall, MRR, NDCG, hit rate.

Gains come from human grades (0-3) when present, falling back to binary
relevance from `relevant_ids`. NDCG uses `gain / log2(rank + 1)` with the ideal
ordering as its normalizer, so a strategy that ranks a grade-3 document above
a grade-1 document scores higher than one that reverses them.

All functions are pure and deterministic: same ranking, same numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from faculty_radar.models import RankedResult, RetrievalMetrics


@dataclass(frozen=True)
class RetrievalMetricsComputer:
    """Scores one benchmark case at the configured cutoffs."""

    k_values: tuple[int, ...] = (1, 5, 10)

    def score_case(
        self,
        relevant_ids: list[str],
        results: list[RankedResult],
        graded: dict[str, int] | None = None,
    ) -> dict[str, float | dict[str, float]]:
        """Per-case metrics; empty results score zero, never error."""
        gains = _gains(relevant_ids, graded or {}, results)
        relevant_count = sum(1 for g in gains if g > 0)
        first_rank = next((i for i, g in enumerate(gains, start=1) if g > 0), None)

        precision = {str(k): _precision_at(gains, k) for k in self.k_values}
        recall = {str(k): _recall_at(gains, k, relevant_count) for k in self.k_values}
        ndcg = {str(k): _ndcg_at(gains, k) for k in self.k_values}
        hit_rate = {str(k): 1.0 if any(gains[:k]) else 0.0 for k in self.k_values}
        return {
            "precision_at_k": precision,
            "recall_at_k": recall,
            "mrr": 1.0 / first_rank if first_rank is not None else 0.0,
            "ndcg_at_k": ndcg,
            "hit_rate_at_k": hit_rate,
        }


def score_case(
    relevant_ids: list[str],
    results: list[RankedResult],
    k_values: tuple[int, ...] = (1, 5, 10),
    graded: dict[str, int] | None = None,
) -> dict[str, float | dict[str, float]]:
    """Convenience entry point for scoring one case."""
    return RetrievalMetricsComputer(k_values).score_case(relevant_ids, results, graded)


def average_metrics(
    per_case: list[dict],
    k_values: tuple[int, ...],
    graded_queries: int,
) -> RetrievalMetrics:
    """Mean each metric over graded queries; ungraded input stays ungraded."""
    if not per_case:
        return RetrievalMetrics(
            graded_queries=graded_queries,
            ungraded=True,
            note="no graded queries; nothing to average",
        )

    def _mean(values) -> float:
        items = list(values)
        return sum(items) / len(items)

    return RetrievalMetrics(
        precision_at_k={
            str(k): _mean(c["precision_at_k"][str(k)] for c in per_case) for k in k_values
        },
        recall_at_k={str(k): _mean(c["recall_at_k"][str(k)] for c in per_case) for k in k_values},
        mrr=_mean(c["mrr"] for c in per_case),
        ndcg_at_k={str(k): _mean(c["ndcg_at_k"][str(k)] for c in per_case) for k in k_values},
        hit_rate_at_k={
            str(k): _mean(c["hit_rate_at_k"][str(k)] for c in per_case) for k in k_values
        },
        graded_queries=graded_queries,
        ungraded=False,
    )


def _gains(
    relevant_ids: list[str], graded: dict[str, int], results: list[RankedResult]
) -> list[float]:
    """Per-rank gains: human grade when judged, else binary relevance."""
    relevant = set(relevant_ids)
    gains = []
    for result in results:
        if result.id in graded:
            gains.append(float(graded[result.id]))
        elif result.id in relevant:
            gains.append(1.0)
        else:
            gains.append(0.0)
    return gains


def _precision_at(gains: list[float], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(1 for g in gains[:k] if g > 0) / k


def _recall_at(gains: list[float], k: int, relevant_count: int) -> float:
    if k <= 0 or relevant_count == 0:
        return 0.0
    return sum(1 for g in gains[:k] if g > 0) / relevant_count


def _ndcg_at(gains: list[float], k: int) -> float:
    if k <= 0:
        return 0.0
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains[:k], start=1))
    ideal = sorted(gains, reverse=True)
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal[:k], start=1))
    return dcg / idcg if idcg > 0 else 0.0
