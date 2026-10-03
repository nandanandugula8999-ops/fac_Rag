"""Stage 15 tests: grounded answers, verification verdicts, and the LLM boundary."""

from __future__ import annotations

import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.llm.cache import LlmCache, cached_answer_key
from faculty_radar.llm.generate import LlmError, generate_answer
from faculty_radar.models import (
    Answer,
    AnswerCitation,
    AnswerClaim,
    ExpertiseType,
    Status,
    VerificationStatus,
)
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import build_paths
from faculty_radar.rag.pipeline import RagPipeline, _fit_context, answer_query
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.verification.checks import verify_answer
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"


@pytest.fixture
def pipeline(engine_settings):
    authors = normalize_authors(AUTHORS)
    works = normalize_works(WORKS)
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    consent = ConsentRegistry(
        {rid: ConsentEntry(rid, consented=True) for rid in (WEI, LUIS, PRIYA, SOUTHPORT)},
        enforce=True,
    )
    profiles = link_faculty(
        resolved.researchers, authors, works, engine_settings, consent=consent, store=False
    )
    documents = build_corpus(profiles, works, engine_settings, store=False)
    paths = build_paths(engine_settings)
    return {
        "profiles": profiles,
        "works": works,
        "documents": documents,
        "rag": RagPipeline(profiles, works, documents, engine_settings, paths),
    }


# --------------------------------------------------------------------------
# End-to-end grounded answers
# --------------------------------------------------------------------------


class TestGroundedAnswers:
    def test_answer_is_verified_and_cited(self, pipeline):
        answer = pipeline["rag"].answer("graph neural networks")

        assert answer.status is Status.OK
        assert answer.verified is True
        assert answer.claims
        assert answer.llm_model == "extractive-v1"
        for claim in answer.claims:
            assert claim.status is VerificationStatus.SUPPORTED
            assert claim.citations

    def test_every_citation_resolves_to_the_corpus(self, pipeline):
        answer = pipeline["rag"].answer("graph neural networks")
        doc_ids = {doc.doc_id for doc in pipeline["documents"]}

        for citation in answer.citations:
            assert citation.quote
            assert any(citation.evidence_id.startswith(doc_id) for doc_id in doc_ids)

    def test_no_evidence_query_is_insufficient(self, pipeline):
        answer = pipeline["rag"].answer("xylophone concerto")

        assert answer.status is Status.INSUFFICIENT_EVIDENCE
        assert answer.claims == []
        assert answer.verified is False

    def test_answer_carries_matches_and_evidence(self, pipeline):
        answer = pipeline["rag"].answer("protein folding dynamics")

        assert answer.expertise_matches
        assert answer.evidence
        assert answer.expertise_matches[0].faculty_id == PRIYA

    def test_context_budget_drops_whole_items(self, pipeline, engine_settings):
        rag = pipeline["rag"]
        report = rag.engine.find_experts("graph neural networks")
        from faculty_radar.evidence.selection import select_evidence

        evidence = select_evidence(report.matches, engine_settings)

        # Nothing fits in 10 chars, so nothing is returned - and crucially,
        # no quote is ever truncated to fit.
        assert _fit_context(evidence, max_chars=10) == []

    def test_convenience_entry_point(self, pipeline, engine_settings):
        answer = answer_query(
            "protein folding dynamics",
            pipeline["profiles"],
            pipeline["works"],
            pipeline["documents"],
            engine_settings,
        )

        assert answer.status is Status.OK
        assert answer.verified is True


# --------------------------------------------------------------------------
# LLM boundary
# --------------------------------------------------------------------------


class TestLlmBoundary:
    def test_extractive_restates_only_evidence(self, pipeline, engine_settings):
        rag = pipeline["rag"]
        report = rag.engine.find_experts("protein folding dynamics")
        from faculty_radar.evidence.selection import select_evidence

        evidence = select_evidence(report.matches, engine_settings)
        names = {p.faculty_id: p.name for p in pipeline["profiles"]}
        answer = generate_answer("protein folding dynamics", evidence, names, engine_settings)

        for claim in answer.claims:
            for citation in claim.citations:
                assert citation.quote in answer.answer_text
        assert "Priya Raghavan" in answer.answer_text

    def test_empty_evidence_is_insufficient(self, pipeline, engine_settings):
        answer = generate_answer("anything", [], {}, engine_settings)

        assert answer.status is Status.INSUFFICIENT_EVIDENCE

    def test_unimplemented_provider_is_explicit(self, pipeline, engine_settings):
        # Unknown provider names fail loudly instead of silently degrading.
        settings = engine_settings.model_copy(deep=True)
        settings.llm.provider = "not_a_provider"

        with pytest.raises(LlmError, match="unknown"):
            generate_answer("q", [], {}, settings)

    def test_research_provider_keeps_faculty_extractive(self, pipeline, engine_settings):
        # Faculty generation stays extractive even when Research AI uses groq.
        from faculty_radar.evidence.selection import select_evidence

        settings = engine_settings.model_copy(deep=True)
        settings.llm.provider = "groq"
        report = pipeline["rag"].engine.find_experts("protein folding dynamics")
        evidence = select_evidence(report.matches, engine_settings)
        names = {p.faculty_id: p.name for p in pipeline["profiles"]}
        answer = generate_answer("protein folding dynamics", evidence, names, settings)

        assert answer.status is Status.OK
        assert answer.claims, "faculty answer must carry evidence-backed claims"

    def test_answer_cache_replays_identical_inputs(self, pipeline, engine_settings):
        paths = build_paths(engine_settings)
        rag = pipeline["rag"]
        report = rag.engine.find_experts("protein folding dynamics")
        from faculty_radar.evidence.selection import select_evidence

        evidence = select_evidence(report.matches, engine_settings)
        names = {p.faculty_id: p.name for p in pipeline["profiles"]}
        first = generate_answer("protein folding dynamics", evidence, names, engine_settings, paths)
        second = generate_answer(
            "protein folding dynamics", evidence, names, engine_settings, paths
        )

        key = cached_answer_key("extractive-v1", "protein folding dynamics", evidence)
        assert (LlmCache(paths).cache_dir / f"{key}.json").exists()
        assert second == first


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


class TestVerification:
    def test_fabricated_citation_is_unsupported(self, pipeline, engine_settings):
        answer = Answer(
            query="q",
            answer_text="Someone did something.",
            claims=[
                AnswerClaim(
                    text="Someone did something.",
                    citations=[
                        AnswerCitation(
                            evidence_id="doc:imaginary",
                            work_id="W999",
                            quote="entirely made up",
                        )
                    ],
                )
            ],
        )
        report = verify_answer(answer, pipeline["documents"], pipeline["works"], engine_settings)

        assert report.verified is False
        assert report.answer.claims[0].status is VerificationStatus.UNSUPPORTED
        assert report.fabricated_citations == ["doc:imaginary"]

    def test_altered_quote_fails_verbatim_check(self, pipeline, engine_settings):
        real = pipeline["rag"].answer("protein folding dynamics")
        tampered = real.claims[0].model_copy(deep=True)
        tampered.citations[0] = tampered.citations[0].model_copy(
            update={"quote": tampered.citations[0].quote + " (and more)"}
        )
        answer = real.model_copy(update={"claims": [tampered], "verified": False})
        report = verify_answer(answer, pipeline["documents"], pipeline["works"], engine_settings)

        assert report.answer.claims[0].status is VerificationStatus.UNSUPPORTED

    def test_citation_without_claim_evidence_is_unsupported(self, pipeline, engine_settings):
        answer = Answer(
            query="q",
            answer_text="A bare assertion.",
            claims=[AnswerClaim(text="A bare assertion.", citations=[])],
        )
        report = verify_answer(answer, pipeline["documents"], pipeline["works"], engine_settings)

        assert report.answer.claims[0].status is VerificationStatus.UNSUPPORTED
        assert report.verified is False

    def test_overstated_expertise_label_is_capped(self, pipeline, engine_settings):
        real = pipeline["rag"].answer("protein folding dynamics")
        claim = real.claims[0].model_copy(
            update={
                "expertise_type": ExpertiseType.STATED,
                "status": VerificationStatus.UNSUPPORTED,
            }
        )
        answer = real.model_copy(update={"claims": [claim], "verified": False})
        report = verify_answer(answer, pipeline["documents"], pipeline["works"], engine_settings)

        # Priya declared no stated topics: the STATED label cannot stand.
        assert report.answer.claims[0].status is VerificationStatus.PARTIALLY_SUPPORTED

    def test_verification_report_rates_support(self, pipeline):
        answer = pipeline["rag"].answer("graph neural networks")
        report = verify_answer(answer, pipeline["documents"], pipeline["works"])

        assert report.support_rate == 1.0
        assert report.citation_correctness == 1.0
