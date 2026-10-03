"""Post-generation claim checking against the ingested corpus.

Verification is deliberately mechanical: set membership for citations,
substring matching for quotes, label comparison for expertise types. There is
no language model in this loop, so there is nothing here that can be talked
into approving a claim.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import (
    Answer,
    AnswerCitation,
    ClaimCheck,
    CorpusDocument,
    DocumentType,
    ExpertiseType,
    NormalizedWork,
    VerificationReport,
    VerificationStatus,
)

logger = get_logger(__name__)


def verify_answer(
    answer: Answer,
    documents: list[CorpusDocument],
    works: list[NormalizedWork] | None = None,
    settings: Settings | None = None,
) -> VerificationReport:
    """Check every claim and return the answer with verdicts attached."""
    settings = settings or get_settings()
    corpus = _CorpusIndex(documents, works or [])

    checks: list[ClaimCheck] = []
    for claim in answer.claims:
        checks.append(_check_claim(claim, corpus))

    fabricated = sorted({cite for check in checks for cite in check.invented_citations})
    verified_claims = [
        claim.model_copy(update={"status": check.status, "verification_note": check.note})
        for claim, check in zip(answer.claims, checks, strict=True)
    ]
    verified = bool(checks) and all(
        check.status is VerificationStatus.SUPPORTED for check in checks
    )
    warnings = list(answer.warnings)
    if fabricated:
        warnings.append(f"{len(fabricated)} fabricated citation(s) detected")
    if any(c.status is VerificationStatus.UNSUPPORTED for c in checks):
        verified = False
        warnings.append("answer contains unsupported claims")

    verified_answer = answer.model_copy(
        update={"claims": verified_claims, "verified": verified, "warnings": warnings}
    )
    supported = sum(
        1
        for check in checks
        if check.status in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED)
    )
    report = VerificationReport(
        answer=verified_answer,
        checks=checks,
        fabricated_citations=fabricated,
        verified=verified,
        notes=[f"support rate {supported}/{len(checks)}"] if checks else ["no claims to verify"],
    )
    logger.debug(
        "verification complete",
        extra={
            "claims": len(checks),
            "verified": verified,
            "fabricated": len(fabricated),
        },
    )
    return report


def _check_claim(claim, corpus: _CorpusIndex) -> ClaimCheck:
    """Verify one claim's citations and expertise label."""
    if not claim.citations:
        return ClaimCheck(
            claim=claim.text,
            status=VerificationStatus.UNSUPPORTED,
            support_score=0.0,
            note="claim carries no citations",
        )

    matched: list[AnswerCitation] = []
    invented: list[str] = []
    verified_count = 0
    for citation in claim.citations:
        doc = corpus.resolve(citation)
        if doc is None:
            invented.append(citation.evidence_id)
            continue
        matched.append(citation)
        if _quote_present(citation.quote, doc.text):
            verified_count += 1

    if not matched:
        return ClaimCheck(
            claim=claim.text,
            status=VerificationStatus.UNSUPPORTED,
            matched_citations=[],
            invented_citations=invented,
            support_score=0.0,
            note="no citation resolves to an ingested record",
        )

    support = verified_count / len(claim.citations)
    if verified_count == len(claim.citations):
        status = VerificationStatus.SUPPORTED
        note = f"all {len(claim.citations)} citation(s) resolve with verbatim quotes"
    elif verified_count > 0:
        status = VerificationStatus.PARTIALLY_SUPPORTED
        note = f"{verified_count}/{len(claim.citations)} citation(s) verified verbatim"
    else:
        status = VerificationStatus.UNSUPPORTED
        note = "citations resolve but no quote appears verbatim"

    capped = _cap_for_label(claim, matched, corpus)
    if capped is not None and status is VerificationStatus.SUPPORTED:
        status = VerificationStatus.PARTIALLY_SUPPORTED
        note += f"; {capped}"

    return ClaimCheck(
        claim=claim.text,
        status=status,
        matched_evidence_ids=[c.evidence_id for c in matched],
        matched_citations=matched,
        invented_citations=invented,
        support_score=support,
        note=note,
    )


def _cap_for_label(claim, matched: list[AnswerCitation], corpus: _CorpusIndex) -> str | None:
    """A claim must not advertise stronger evidence than its citations carry.

    A STATED claim needs at least one cited document flagged as stated
    expertise; an EVIDENCE_BASED claim needs at least one cited publication.
    """
    docs = [corpus.resolve(citation) for citation in matched]
    docs = [doc for doc in docs if doc is not None]
    if claim.expertise_type is ExpertiseType.STATED and not any(doc.is_stated for doc in docs):
        return "claim labeled STATED but no cited document is stated expertise"
    if claim.expertise_type is ExpertiseType.EVIDENCE_BASED and not any(
        doc.document_type is DocumentType.PUBLICATION for doc in docs
    ):
        return "claim labeled EVIDENCE_BASED but no cited document is a publication"
    return None


def _quote_present(quote: str, text: str) -> bool:
    """Verbatim containment after whitespace normalization."""
    if not quote or not quote.strip():
        return False
    normalized_quote = " ".join(quote.split())
    normalized_text = " ".join(text.split())
    return normalized_quote in normalized_text


class _CorpusIndex:
    """Lookup of every citable identifier in the ingested snapshot."""

    def __init__(self, documents: list[CorpusDocument], works: list[NormalizedWork]) -> None:
        self.by_doc_id = {doc.doc_id: doc for doc in documents}
        self.by_work_id: dict[str, CorpusDocument] = {}
        self.known_dois: set[str] = set()
        self.known_urls: set[str] = set()
        for doc in documents:
            if doc.work_id and doc.work_id not in self.by_work_id:
                self.by_work_id[doc.work_id] = doc
            if doc.doi:
                self.known_dois.add(doc.doi)
            if doc.source_url:
                self.known_urls.add(doc.source_url)
        for work in works:
            if work.doi:
                self.known_dois.add(work.doi)
            if work.citation_url:
                self.known_urls.add(work.citation_url)

    def resolve(self, citation: AnswerCitation) -> CorpusDocument | None:
        """Find the cited document, or None when the citation is fabricated."""
        if citation.evidence_id and citation.evidence_id in self.by_doc_id:
            return self.by_doc_id[citation.evidence_id]
        if citation.evidence_id:
            for doc_id, doc in self.by_doc_id.items():
                if citation.evidence_id.startswith(doc_id):
                    return doc
        if citation.work_id and citation.work_id in self.by_work_id:
            return self.by_work_id[citation.work_id]
        if citation.doi and citation.doi in self.known_dois:
            return next(
                (doc for doc in self.by_doc_id.values() if doc.doi == citation.doi),
                None,
            )
        if citation.source_url and citation.source_url in self.known_urls:
            return next(
                (doc for doc in self.by_doc_id.values() if doc.source_url == citation.source_url),
                None,
            )
        return None
