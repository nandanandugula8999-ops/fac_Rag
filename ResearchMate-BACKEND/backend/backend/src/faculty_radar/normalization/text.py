"""Deterministic text canonicalization.

Everything here is pure and side-effect free, because these functions are the
basis for every comparison in the system: name matching in entity resolution,
topic matching in the expertise engine, and tokenization in BM25. A subtle
inconsistency here would produce confidently wrong merges, so the functions are
kept deliberately boring and separately tested.

No fuzzy matching libraries: these are exact canonicalizations, and any notion
of similarity belongs in `resolution` where it can be scored and explained.
"""

from __future__ import annotations

import re
import unicodedata

# Words that carry no discriminating power in a researcher name.
_NAME_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+")

# Tokens dropped from query and document text. Kept deliberately short: over
# aggressive stopword removal hurts BM25 on short abstracts.
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "their",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "we",
        "our",
        "us",
        "you",
        "your",
    ]
)


def strip_accents(text: str) -> str:
    """Remove diacritics: 'José' -> 'Jose'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def canonical_key(text: str | None) -> str:
    """Comparison key for a name or topic.

    Case-folded, accent-free, punctuation-free, whitespace-collapsed. Two
    strings with the same key are *candidates* for a match, never proof of one:
    the decision belongs to `resolution`, which weighs evidence.
    """
    if not text:
        return ""
    text = strip_accents(text).casefold()
    text = _NAME_PUNCT.sub(" ", text)
    return collapse_whitespace(text)


def name_tokens(text: str | None) -> tuple[str, ...]:
    """Tokens of a name in canonical form, for set-overlap comparisons.

    Stopwords are deliberately *not* removed here. Particles such as "van",
    "de" and "bin" are part of the surname, so dropping them would make
    "Ludwig van Beethoven" and "Beethoven, Ludwig" look like different names.
    """
    return tuple(tokenize(canonical_key(text), drop_stopwords=False))


def tokenize(text: str | None, *, drop_stopwords: bool = True) -> list[str]:
    """Lowercase alphanumeric tokens, accent-free.

    Single tokens rather than stems: a stemmer would conflate distinct research
    terms ("graph" / "graphs") that BM25 is expected to treat with term-frequency
    saturation, and stemming is a documented non-goal at this stage.
    """
    if not text:
        return []
    tokens = _TOKEN.findall(strip_accents(text).casefold())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])")
_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
    "doi ",
)
_DOI_CLEAN = re.compile(r"[^\w./()-]")


def extract_orcid(value: str | None) -> str | None:
    """Pull a bare 16-digit ORCID out of a URL, identifier, or free string."""
    if not value:
        return None
    match = _ORCID_RE.search(value)
    if not match:
        return None
    orcid = match.group(1).upper()
    # ORCID's check character is X for identifiers that predate the standard.
    return orcid if not orcid.endswith("XXX") else None


def normalize_doi(value: str | None) -> str | None:
    """Reduce any DOI spelling to its bare `10.x/suffix` form.

    Returns None rather than a guess when the input is not recognizably a DOI.
    Rule 2: better no DOI than a fabricated one.
    """
    if not value:
        return None
    doi = value.strip().casefold()
    for prefix in _DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix) :].strip()
            break
    if not doi.startswith("10."):
        return None
    doi = _DOI_CLEAN.sub("", doi)
    return doi or None


def doi_url(doi: str | None) -> str | None:
    """Canonical resolvable URL for a normalized DOI."""
    return f"https://doi.org/{doi}" if doi else None


def normalize_ror(value: str | None) -> str | None:
    """Reduce a ROR identifier to `https://ror.org/0abc...`."""
    if not value:
        return None
    ror = value.strip().casefold().rstrip("/")
    if ror.startswith("https://ror.org/"):
        ror = ror[len("https://ror.org/") :]
    elif ror.startswith("http://ror.org/"):
        ror = ror[len("http://ror.org/") :]
    if not re.fullmatch(r"0[a-hj-km-np-tv-z0-9]{6}\d{2}", ror):
        return None
    return f"https://ror.org/{ror}"


def openalex_id(url_or_id: str | None) -> str | None:
    """Extract the short ID from an OpenAlex URL, e.g. 'A5023888391'."""
    if not url_or_id:
        return None
    tail = url_or_id.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail and not tail.isspace() else None


def normalize_title(value: str | None) -> str | None:
    """Canonical comparison form of a publication title."""
    if not value:
        return None
    text = collapse_whitespace(value)
    return text or None


def truncate_words(text: str, limit: int) -> str:
    """Trim to a word budget without cutting mid-word."""
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit])
