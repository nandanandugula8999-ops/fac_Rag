"""Evidence and citation verification.

Stage 15c of the pipeline, and the reason this system can be trusted over a
plain chatbot. Every claim is checked after generation, never inside the
prompt alone:

  * each citation must resolve to a real ingested record: a known document,
    work, DOI, or source URL. Anything else is recorded as fabricated.
  * each cited quote must appear verbatim in the cited document's text.
    Paraphrases and near-matches do not count.
  * a claim's expertise label must not outrun its citations: a STATED claim
    needs stated evidence behind it.

Outcomes per claim are `supported`, `partially_supported`, or `unsupported`.
An answer is marked verified only when every claim is supported and no
citation was fabricated.
"""

from faculty_radar.verification.checks import VerificationReport, verify_answer

__all__ = [
    "VerificationReport",
    "verify_answer",
]
