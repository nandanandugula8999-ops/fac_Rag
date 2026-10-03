"""Literature search service (plan.md section 9).

Reuses the existing pipeline: DiscoveryService (OpenAlex live) -> normalize ->
RagPipeline hybrid retrieval, then projects works into paper cards.
No papers are fabricated: empty result returns explicit no-evidence payload.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_settings


def search_literature(
    query: str,
    *,
    top_k: int = 10,
    year: int | None = None,
    open_access_only: bool = False,
    settings: Settings | None = None,
    discovery=None,
) -> dict:
    resolved = settings or get_settings()
    q = (query or "").strip()
    if not q:
        return {"query": query, "papers": [], "status": "empty_query"}

    if discovery is None:
        from faculty_radar.discovery.service import DiscoveryService

        discovery = DiscoveryService(settings=resolved)
    found = discovery.discover(q)
    papers: list[dict] = []
    for work in found.works:
        if year is not None and work.year != year:
            continue
        is_oa = any((loc.is_oa for loc in (work.locations or [])),)
        if open_access_only and not is_oa:
            continue
        topics = [t.name for t in (work.topics or [])][:5]
        keywords = [k.name for k in (work.keywords or [])][:5]
        papers.append(
            {
                "id": work.openalex_id,
                "title": work.title,
                "year": work.year,
                "doi": work.doi,
                "citation_url": work.citation_url,
                "abstract": (work.abstract or "")[:1200],
                "topics": topics,
                "keywords": keywords,
                "cited_by_count": work.cited_by_count,
                "is_open_access": bool(is_oa),
                "type": work.type,
            }
        )
        if len(papers) >= top_k:
            break
    # Most-cited first is already discovery order; keep stable.
    return {
        "query": q,
        "papers": papers,
        "status": "ok" if papers else "no_evidence",
        "works_retrieved": found.works_retrieved,
        "provider": found.provider,
        "cached": found.cached,
    }


def get_paper_detail(openalex_id: str, *, settings: Settings | None = None) -> dict | None:
    """Fetch one work by OpenAlex ID for Paper Intelligence view."""
    from faculty_radar.ingestion.client import OpenAlexClient

    resolved = settings or get_settings()
    client = OpenAlexClient(resolved.openalex)
    try:
        payload = client.get(f"works/{openalex_id}")
    except Exception:
        return None
    if not payload:
        return None
    from faculty_radar.normalization.works import normalize_works

    works = normalize_works([payload])
    if not works:
        return None
    w = works[0]
    return {
        "id": w.openalex_id,
        "title": w.title,
        "year": w.year,
        "doi": w.doi,
        "citation_url": w.citation_url,
        "abstract": w.abstract,
        "topics": [t.name for t in (w.topics or [])],
        "keywords": [k.name for k in (w.keywords or [])],
        "concepts": [c.name for c in (w.concepts or [])][:10],
        "cited_by_count": w.cited_by_count,
        "referenced_works": (w.referenced_work_ids or [])[:20],
        "locations": [
            {"landing_page_url": loc.landing_page_url, "pdf_url": loc.pdf_url, "is_oa": loc.is_oa}
            for loc in (w.locations or [])
        ],
    }
