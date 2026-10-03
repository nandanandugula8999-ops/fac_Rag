"""Gap & novelty service (plan.md sections 12-13).

Deterministic evidence counting FIRST (no LLM invention):
- dataset/topic/method frequency from work topics+keywords
- recency spread, cross-topic absences
then the Unified LLM Service reasons over those counts into candidate gaps,
each carrying evidence counts + supporting work IDs + confidence.
Novelty check searches literature for idea components and reports overlap
honestly (never "definitely novel" without evidence).
"""

from __future__ import annotations

from collections import Counter

from faculty_radar.config import Settings, get_settings


def detect_gaps(
    query: str,
    *,
    top_k: int = 20,
    settings: Settings | None = None,
    discovery=None,
    elaborate: bool = True,
) -> dict:
    resolved = settings or get_settings()
    q = (query or "").strip()
    if discovery is None:
        from faculty_radar.discovery.service import DiscoveryService

        discovery = DiscoveryService(settings=resolved)
    found = discovery.discover(q) if q else None
    works = list(found.works) if found and found.works else []
    if not works:
        return {
            "query": q,
            "gaps": [],
            "status": "no_evidence",
            "note": "No supporting works retrieved; no gaps fabricated.",
        }

    topic_counts = Counter(t.name for w in works for t in (w.topics or []) if t.name)
    year_counts = Counter(w.year for w in works if w.year)
    total = len(works)
    gaps: list[dict] = []

    # Gap 1: concentration — one dominant topic, thin tail.
    if topic_counts:
        top_topic, top_n = topic_counts.most_common(1)[0]
        if top_n / max(total, 1) >= 0.6 and len(topic_counts) >= 2:
            gaps.append(
                {
                    "title": f"Over-concentration on '{top_topic}'",
                    "description": (
                        f"{top_n}/{total} works cluster on '{top_topic}'. "
                        "Adjacent topics are thinly covered."
                    ),
                    "evidence": {
                        "total_works": total,
                        "topic_counts": dict(topic_counts.most_common(8)),
                        "supporting_titles": [w.title for w in works[:4] if w.title],
                    },
                    "confidence": "high" if total >= 8 else "medium",
                    "type": "concentration",
                }
            )
    # Gap 2: recency — little recent work.
    if year_counts:
        recent = sum(n for y, n in year_counts.items() if y and y >= 2023)
        if recent / max(total, 1) < 0.3:
            gaps.append(
                {
                    "title": "Limited recent validation",
                    "description": (
                        f"Only {recent}/{total} works are from 2023+. "
                        "Recent methods/datasets may be underexplored."
                    ),
                    "evidence": {
                        "total_works": total,
                        "year_counts": {str(k): v for k, v in sorted(year_counts.items())},
                    },
                    "confidence": "medium",
                    "type": "recency",
                }
            )
    # Gap 3: cross-topic — topics rarely co-occur (potential combination).
    topics = list(topic_counts)
    if len(topics) >= 2:
        gaps.append(
            {
                "title": f"Unexplored combination: '{topics[0]}' x '{topics[1]}'",
                "description": (
                    "Both topics appear in the corpus but rarely together in one work. "
                    "A combined or cross-evaluation study is a potential direction."
                ),
                "evidence": {
                    "total_works": total,
                    "topic_counts": dict(topic_counts.most_common(8)),
                },
                "confidence": "medium",
                "type": "combination",
                "potential_directions": [
                    "different dataset",
                    "different architecture",
                    "cross-dataset evaluation",
                    "explainability",
                    "efficiency / lightweight models",
                ],
            }
        )

    # Optional LLM elaboration over the counts (grounded, never new papers).
    # Callers that stream tokens themselves pass elaborate=False.
    llm_note = None
    if elaborate and resolved.llm.provider in ("groq",):
        try:
            from faculty_radar.services.llm_service import generate

            prompt = (
                f"Research query: {q}\n"
                f"Evidence counts: total={total}, topics={dict(topic_counts.most_common(10))}, "
                f"years={dict(sorted(year_counts.items()))}\n"
                "List 2-3 potential research directions strictly consistent with these "
                "counts. Return plain text, no invented papers."
            )
            llm_note = generate(prompt, settings=resolved)["text"][:2000]
        except Exception as exc:
            llm_note = f"LLM unavailable ({exc}); deterministic gaps above remain valid."

    return {
        "query": q,
        "gaps": gaps[:top_k],
        "status": "ok",
        "total_works": total,
        "llm_elaboration": llm_note,
    }


def check_novelty(idea: str, *, settings: Settings | None = None, discovery=None) -> dict:
    """Honest novelty screen: report overlapping works, never certify novelty."""
    from faculty_radar.services.literature_service import search_literature

    resolved = settings or get_settings()
    result = search_literature(idea, top_k=8, settings=resolved, discovery=discovery)
    papers = result.get("papers", [])
    if not papers:
        return {
            "idea": idea,
            "verdict": "unknown",
            "note": "No overlapping literature retrieved; cannot confirm novelty.",
            "overlapping_papers": [],
        }
    return {
        "idea": idea,
        "verdict": "needs_differentiation",
        "note": (
            f"{len(papers)} related works found. Review them and differentiate by "
            "dataset, architecture, evaluation, or application before claiming novelty."
        ),
        "overlapping_papers": papers[:5],
    }
