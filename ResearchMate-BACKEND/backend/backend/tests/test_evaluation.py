"""Stage 16 tests: graded metrics math and the honesty accounting."""

from __future__ import annotations

import math

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.evaluation.metrics import (
    RetrievalMetricsComputer,
    average_metrics,
    score_case,
)
from faculty_radar.evaluation.suite import EvaluationRunner, evaluate_strategy
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import BenchmarkCase, RankedResult
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.retrieval.hybrid import HybridRetriever
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"


def _result(id: str, rank: int, score: float = 1.0) -> RankedResult:
    return RankedResult(id=id, score=score / rank, rank=rank)


def _relevant(*ids: str) -> list[str]:
    return list(ids)


class TestMetricMath:
    def test_perfect_ranking_scores_one(self):
        computer = RetrievalMetricsComputer((1, 2))

        scored = computer.score_case(
            _relevant("a", "b"), [_result("a", 1), _result("b", 2), _result("c", 3)]
        )

        assert scored["precision_at_k"] == {"1": 1.0, "2": 1.0}
        assert scored["recall_at_k"] == {"1": 0.5, "2": 1.0}
        assert scored["mrr"] == 1.0
        assert scored["ndcg_at_k"] == {"1": 1.0, "2": 1.0}
        assert scored["hit_rate_at_k"] == {"1": 1.0, "2": 1.0}

    def test_first_relevant_at_rank_two(self):
        scored = score_case(
            _relevant("a", "b"), [_result("c", 1), _result("a", 2), _result("b", 3)], (1, 3)
        )

        assert scored["mrr"] == 0.5
        assert scored["precision_at_k"]["1"] == 0.0
        assert scored["hit_rate_at_k"]["1"] == 0.0
        assert scored["hit_rate_at_k"]["3"] == 1.0
        assert scored["recall_at_k"]["3"] == 1.0

    def test_graded_gains_reward_better_ordering(self):
        graded = {"a": 3, "b": 1}
        good = score_case([], [_result("a", 1), _result("b", 2)], (2,), graded)
        bad = score_case([], [_result("b", 1), _result("a", 2)], (2,), graded)

        assert good["ndcg_at_k"]["2"] == 1.0
        assert bad["ndcg_at_k"]["2"] < 1.0
        assert bad["ndcg_at_k"]["2"] == (
            (1 / math.log2(2) + 3 / math.log2(3)) / (3 / math.log2(2) + 1 / math.log2(3))
        )

    def test_empty_results_score_zero(self):
        scored = score_case(_relevant("a", "b"), [], (1, 5))

        assert scored["mrr"] == 0.0
        assert scored["precision_at_k"] == {"1": 0.0, "5": 0.0}
        assert scored["ndcg_at_k"] == {"1": 0.0, "5": 0.0}

    def test_averaging_is_a_mean(self):
        averaged = average_metrics(
            [
                score_case(_relevant("a", "b"), [_result("a", 1), _result("b", 2)], (1,)),
                score_case(_relevant("a", "b"), [_result("c", 1)], (1,)),
            ],
            (1,),
            graded_queries=2,
        )

        assert averaged.precision_at_k == {"1": 0.5}
        assert averaged.mrr == 0.5
        assert averaged.graded_queries == 2
        assert averaged.ungraded is False

    def test_no_cases_stays_ungraded(self):
        averaged = average_metrics([], (1,), graded_queries=0)

        assert averaged.ungraded is True


class TestEvaluationSuite:
    def _benchmark(self, engine_settings):
        authors = normalize_authors(AUTHORS)
        works = normalize_works(WORKS)
        resolved = resolve_researchers(authors, works, engine_settings, store=False)
        consent = ConsentRegistry(
            {rid: ConsentEntry(rid, consented=True) for rid in (WEI, LUIS, PRIYA, SOUTHPORT)},
            enforce=True,
        )
        profiles = link_faculty(
            resolved.researchers,
            authors,
            works,
            engine_settings,
            consent=consent,
            store=False,
        )
        documents = build_corpus(profiles, works, engine_settings, store=False)
        retriever = HybridRetriever(documents, engine_settings)
        by_work = {}
        for doc in documents:
            if doc.work_id:
                by_work.setdefault(doc.work_id, doc.doc_id)
        gnn = BenchmarkCase(
            case_id="gnn",
            query="graph neural networks",
            category="technical",
            relevant_ids=[by_work[w] for w in ("W1001", "W1002", "W1005") if w in by_work],
        )
        protein = BenchmarkCase(
            case_id="protein",
            query="protein folding dynamics",
            category="direct",
            relevant_ids=[by_work["W1003"]] if "W1003" in by_work else [],
        )
        ungraded = BenchmarkCase(
            case_id="ungraded",
            query="something nobody judged",
            category="broad",
        )
        return retriever, [gnn, protein, ungraded]

    def test_hybrid_strategy_scores_on_fixture(self, engine_settings):
        retriever, benchmark = self._benchmark(engine_settings)
        settings = engine_settings.model_copy(deep=True)
        settings.evaluation.min_graded_items = 1

        def run_case(case):
            return [
                RankedResult(id=hit.doc_id, score=hit.score, rank=hit.rank or 0)
                for hit in retriever.search(case.query, top_k=5)
            ]

        report = evaluate_strategy("hybrid", benchmark, run_case, settings)

        assert report.metrics.ungraded is False
        assert report.metrics.graded_queries == 2
        assert report.metrics.hit_rate_at_k["1"] == 1.0
        assert report.metrics.precision_at_k["1"] == 1.0
        assert report.insufficient_evidence_rate == 0.0
        assert report.evidence_coverage is None
        assert "excluded" in " ".join(report.notes)

    def test_ungraded_queries_excluded_not_scored(self, engine_settings):
        _, benchmark = self._benchmark(engine_settings)
        settings = engine_settings.model_copy(deep=True)
        settings.evaluation.min_graded_items = 1
        runner = EvaluationRunner(benchmark, settings)

        suite = runner.build_suite([])

        assert suite.ungraded_queries == 1
        assert "excluded" in suite.note

    def test_too_few_graded_queries_marks_ungraded(self, engine_settings):
        _, benchmark = self._benchmark(engine_settings)

        report = evaluate_strategy("hybrid", benchmark, lambda case: [], engine_settings)

        assert report.metrics.ungraded is True
        assert report.metrics.graded_queries == 2
        assert report.insufficient_evidence_rate == 1.0

    def test_empty_benchmark_is_safe(self, engine_settings):
        report = evaluate_strategy("hybrid", [], lambda case: [], engine_settings)

        assert report.insufficient_evidence_rate == 0.0
        assert report.metrics.ungraded is True
