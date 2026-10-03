"""Reconstruction of OpenAlex abstracts.

OpenAlex does not ship abstracts as text. It ships an *inverted index*: a
mapping from token to the list of positions that token occupies. Recovering the
text is a positional sort, which is trivial in the well-formed case and subtly
wrong in several edge cases that are common in real data:

  * positions may overlap between tokens, so `max(positions) + 1` is the real
    length and is not the same as the token count
  * some tokens have no positions at all, and must not silently become empty
    strings that shift every later word
  * punctuation may be absent from the index entirely, so a reconstruction
    cannot be treated as a verbatim copy of the published abstract
  * the index is sometimes an empty dict, which means "no abstract", not
    "an abstract that is empty"

Consequently `reconstruct_abstract` reports whether the text was *recovered*
rather than *verbatim*, and callers must cite the source record rather than
claiming to quote the publisher. This distinction is carried through to
`EvidenceItem.source_type` and to the verification stage.
"""

from __future__ import annotations

from faculty_radar.config import get_logger
from faculty_radar.normalization.text import collapse_whitespace

logger = get_logger(__name__)


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild abstract text from an OpenAlex inverted index.

    Returns None when there is nothing to rebuild. Never returns an empty or
    partial string: an absent abstract and an unparseable one are both reported
    as absent, because citing a truncated abstract is worse than citing none.
    """
    if not inverted_index:
        return None

    # Collect every (position, token) pair, then place each token at its
    # position. Iterating positions rather than tokens is what makes gaps and
    # out-of-order position lists come out right.
    slots: dict[int, str] = {}
    for token, positions in inverted_index.items():
        if not isinstance(positions, (list, tuple)):
            continue
        for position in positions:
            if not isinstance(position, int) or position < 0:
                continue
            # First writer wins: duplicates at one position are a source defect,
            # and taking the first keeps the result deterministic.
            slots.setdefault(position, token)

    if not slots:
        return None

    length = max(slots) + 1
    ordered: list[str] = [slots.get(index, "") for index in range(length)]
    text = collapse_whitespace(" ".join(part for part in ordered if part))
    if not text:
        return None

    logger.debug("abstract reconstructed", extra={"tokens": len(slots), "length": length})
    return text


def abstract_is_verbatim_safe(inverted_index: dict | None) -> bool:
    """True when the index is dense enough that the text is trustworthy.

    A dense index (every position filled) preserves the original word order and
    spacing; a sparse one has had tokens dropped, so the reconstruction is a
    reconstruction rather than a copy.
    """
    if not inverted_index:
        return False
    positions = [
        position
        for value in inverted_index.values()
        if isinstance(value, (list, tuple))
        for position in value
        if isinstance(position, int) and position >= 0
    ]
    if not positions:
        return False
    return len(positions) == len(set(positions)) == max(positions) + 1


def abstract_coverage(inverted_index: dict | None) -> float:
    """Fraction of token slots actually present, 0.0-1.0."""
    if not inverted_index:
        return 0.0
    positions = [
        position
        for value in inverted_index.values()
        if isinstance(value, (list, tuple))
        for position in value
        if isinstance(position, int) and position >= 0
    ]
    if not positions:
        return 0.0
    expected = max(positions) + 1
    return round(len(set(positions)) / expected, 4) if expected else 0.0
