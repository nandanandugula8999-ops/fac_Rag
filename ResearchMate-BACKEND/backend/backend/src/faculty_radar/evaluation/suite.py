"""Benchmark suite runner.

A strategy is any callable mapping a benchmark case to ranked results. The
runner scores each graded case, averages the metrics, and reports the
insufficient-evidence rate: the share of benchmark queries a strategy answers
with nothing at all. An empty answer to a graded query is a miss, not an
abstention, so it scores zero across the board rather than being excluded.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.evaluation.metrics import RetrievalMetricsComputer, average_metrics
from faculty_radar.models import (
    BenchmarkCase,
    EvaluationReport,
    EvaluationSuite,
    RankedResult,
    RelevanceJudgment,
    RetrievalMetrics,
)

logger = get_logger(__name__)

Strategy = Callable[[BenchmarkCase], list[RankedResult]]


@dataclass
class EvaluationRunner:
    """Runs strategies against a human-graded benchmark."""

    benchmark: list[BenchmarkCase]
    settings: Settings | None = None
    judgments: dict[str, RelevanceJudgment] = field(default_factory=dict)
    suite_notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()

    def evaluate_strategy(self, strategy: str, run_case: Strategy) -> EvaluationReport:
        """Score one strategy over the benchmark's graded queries."""
        settings = self.settings or get_settings()
        computer = RetrievalMetricsComputer(tuple(settings.evaluation.k_values))

        graded = [case for case in self.benchmark if _is_graded(case)]
        per_case = []
        for case in graded:
            judgment = self.judgments.get(case.case_id)
            per_case.append(
                computer.score_case(
                    case.relevant_ids,
                    run_case(case),
                    judgment.graded if judgment else None,
                )
            )
        metrics = average_metrics(per_case, tuple(settings.evaluation.k_values), len(graded))
        if len(graded) < settings.evaluation.min_graded_items:
            metrics = RetrievalMetrics(
                graded_queries=len(graded),
                ungraded=True,
                note=(
                    f"only {len(graded)} graded queries, fewer than the "
                    f"minimum {settings.evaluation.min_graded_items}; "
                    "averages would be noise, so none are reported"
                ),
            )

        empty = sum(1 for case in self.benchmark if not run_case(case))
        insufficient_rate = empty / len(self.benchmark) if self.benchmark else 0.0
        notes = [
            f"{len(graded)}/{len(self.benchmark)} queries graded; "
            "ungraded queries excluded from metrics"
        ]
        report = EvaluationReport(
            strategy=strategy,
            metrics=metrics,
            evidence_coverage=None,
            citation_correctness=None,
            entity_resolution_accuracy=None,
            insufficient_evidence_rate=insufficient_rate,
            notes=notes,
        )
        logger.debug(
            "evaluation complete",
            extra={
                "strategy": strategy,
                "graded": len(graded),
                "insufficient_rate": insufficient_rate,
            },
        )
        return report

    def build_suite(self, reports: list[EvaluationReport]) -> EvaluationSuite:
        """Assemble the benchmark, its reports, and the honesty accounting."""
        ungraded = sum(1 for case in self.benchmark if not _is_graded(case))
        return EvaluationSuite(
            benchmark=list(self.benchmark),
            reports=list(reports),
            ungraded_queries=ungraded,
            note=(
                "Metrics are computed only over human-graded queries. Ungraded "
                "queries are excluded rather than scored against assumed relevance."
            ),
        )


def evaluate_strategy(
    strategy: str,
    benchmark: list[BenchmarkCase],
    run_case: Strategy,
    settings: Settings | None = None,
    judgments: dict[str, RelevanceJudgment] | None = None,
) -> EvaluationReport:
    """Convenience entry point for scoring one strategy."""
    return EvaluationRunner(benchmark, settings, judgments or {}).evaluate_strategy(
        strategy, run_case
    )


def _is_graded(case: BenchmarkCase) -> bool:
    return bool(case.relevant_ids)
