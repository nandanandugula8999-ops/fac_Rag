"""Stage runner: executes session stages, yielding REAL progress events.

Each yielded event reflects work that actually happened (real retrieval counts,
real evidence sizes, real LLM tokens or real errors). Nothing is on a timer;
a step is emitted only after its computation completes. UI renders:
  done step -> check, in-flight step -> active, upcoming -> pending.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from faculty_radar.config import Settings, get_settings
from faculty_radar.services import session_service


def _ev(step: str, stage: str, message: str, **extra) -> dict:
    return {"event": step, "stage": stage, "message": message, **extra}


def _concepts(idea: str) -> list[str]:
    from faculty_radar.normalization.text import tokenize

    seen: list[str] = []
    for tok in tokenize(idea):
        if len(tok) > 2 and tok not in seen:
            seen.append(tok)
    return seen[:12]


def run_stages(
    session,
    stages: list[str],
    *,
    settings: Settings | None = None,
    discovery=None,
) -> Iterator[dict]:
    resolved = settings or get_settings()
    if discovery is None:
        from faculty_radar.discovery.service import DiscoveryService

        discovery = DiscoveryService(settings=resolved)
    for stage in stages:
        if stage not in session_service.STAGES or stage == "idea":
            continue
        session_service.touch(session, stage, "active")
        yield _ev("stage_started", stage, f"{session_service.STAGE_LABELS[stage]} started")
        try:
            fn = _STAGE_FNS[stage]
            result = yield from fn(session, resolved, discovery)
            session_service.store_result(session, stage, result)
            session_service.touch(session, stage, "done", result.get("summary", f"{stage} done"))
            yield _ev("stage_done", stage, result.get("summary", "done"), result=result)
        except Exception as exc:  # honest error, never a fake result
            session_service.touch(session, stage, "error", f"{stage} failed: {exc}")
            yield _ev("stage_error", stage, f"{stage} failed: {exc}")
    yield _ev("run_done", "", "run complete")


def _run_faculty(session, settings, discovery):
    idea = session.idea
    yield _ev("progress", "faculty", "Understanding research question")
    concepts = _concepts(idea)
    yield _ev("progress", "faculty", f"Search concepts: {', '.join(concepts[:6]) or '—'}")
    yield _ev("progress", "faculty", "Searching faculty evidence (OpenAlex + hybrid retrieval)")
    found = discovery.discover(idea)
    yield _ev(
        "progress", "faculty",
        f"{len(found.profiles)} researchers, {len(found.documents)} evidence chunks retrieved",
        profiles=len(found.profiles), documents=len(found.documents),
    )
    if not found.profiles or not found.documents:
        return {"summary": "No in-scope faculty evidence found", "matches": [], "status": "no_evidence"}
    from faculty_radar.rag.pipeline import RagPipeline

    pipeline = RagPipeline(list(found.profiles), list(found.works), list(found.documents), settings)
    answer = pipeline.answer(idea)
    matches = [
        {
            "faculty_id": m.faculty_id,
            "faculty_name": m.faculty_name,
            "score": m.score,
            "expertise_type": m.expertise_type.value,
            "matched_topics": m.matched_topics,
            "evidence": [
                {"title": e.title, "year": e.year, "doi": e.doi} for e in m.evidence[:3]
            ],
        }
        for m in answer.expertise_matches[:10]
    ]
    yield _ev("progress", "faculty", f"Analyzing matches: {len(matches)} faculty ranked with evidence")
    return {
        "summary": f"{len(matches)} faculty discovered with evidence",
        "matches": matches,
        "status": answer.status.value,
    }


def _run_literature(session, settings, discovery):
    from faculty_radar.services.literature_service import search_literature

    yield _ev("progress", "literature", "Understanding research question")
    yield _ev("progress", "literature", "Searching literature (OpenAlex)")
    result = search_literature(session.idea, top_k=20, settings=settings, discovery=discovery)
    papers = result.get("papers", [])
    yield _ev("progress", "literature", f"{len(papers)} papers found", count=len(papers))
    if papers:
        years = [p["year"] for p in papers if p.get("year")]
        topics = Counter(t for p in papers for t in (p.get("topics") or []))
        detail = (
            f"years {min(years)}–{max(years)}" if years else "years unknown"
        ) + (f"; top topic '{topics.most_common(1)[0][0]}'" if topics else "")
        yield _ev("progress", "literature", f"Indexing evidence: {detail}")
    return {
        "summary": f"{len(papers)} papers found" if papers else "No relevant research found",
        "papers": papers,
        "status": result.get("status", "ok"),
    }


def _run_analysis(session, settings, discovery):
    papers = (session.results.get("literature") or {}).get("papers", [])
    if not papers:
        raise RuntimeError("no literature in this session — run Literature Search first")
    yield _ev("progress", "analysis", f"Comparing {len(papers)} papers")
    years = sorted(p["year"] for p in papers if p.get("year"))
    topics = Counter(t for p in papers for t in (p.get("topics") or []))
    cited = sorted(papers, key=lambda p: p.get("cited_by_count", 0), reverse=True)[:5]
    oa = sum(1 for p in papers if p.get("is_open_access"))
    yield _ev(
        "progress", "analysis",
        f"Years {years[0]}–{years[-1]}" if years else "Year data sparse",
        total=len(papers), open_access=oa,
    )
    matrix = [
        {
            "title": p.get("title"), "year": p.get("year"),
            "topics": (p.get("topics") or [])[:3],
            "cited_by_count": p.get("cited_by_count", 0),
            "doi": p.get("doi"),
        }
        for p in papers[:12]
    ]
    return {
        "summary": f"{len(papers)} papers compared across year/topic/citation axes",
        "comparison": matrix,
        "top_topics": dict(topics.most_common(8)),
        "most_cited": [p.get("title") for p in cited],
        "open_access_share": f"{oa}/{len(papers)}",
        "status": "ok",
    }


def _run_gaps(session, settings, discovery):
    from faculty_radar.services.gap_service import detect_gaps
    from faculty_radar.services import llm_service

    yield _ev("progress", "gaps", "Analyzing papers for coverage")
    result = detect_gaps(session.idea, settings=settings, discovery=discovery, elaborate=False)
    gaps = result.get("gaps", [])
    yield _ev(
        "progress", "gaps",
        f"Identifying research gaps across {result.get('total_works', 0)} works",
        total_works=result.get("total_works", 0),
    )
    elab = None
    if settings.llm.provider == "groq":
        yield _ev("progress", "gaps", "Generating gap descriptions (streaming)")
        try:
            parts: list[str] = []
            for tok in llm_service.stream(elab_prompt(session, result), settings=settings):
                parts.append(tok)
                yield _ev("token", "gaps", tok)
            elab = "".join(parts)[:2000] or None
        except Exception as exc:
            elab = f"LLM unavailable ({exc}); deterministic gaps above remain valid."
            yield _ev("progress", "gaps", "Llama unavailable — deterministic evidence gaps retained")
    result["llm_elaboration"] = elab
    return {
        "summary": f"{len(gaps)} research gaps identified with evidence" if gaps else "No supporting evidence found",
        "gaps": gaps,
        "llm_elaboration": elab,
        "status": result.get("status", "ok"),
    }


def elab_prompt(session, result) -> str:
    return (
        f"Research idea: {session.idea}\n"
        f"Evidence: {result.get('total_works', 0)} works. "
        f"Gaps: {[g['title'] for g in result.get('gaps', [])]}\n"
        "Describe each gap in 2 sentences, strictly from this evidence. No invented papers."
    )


def _run_direction(session, settings, discovery):
    from faculty_radar.services.gap_service import check_novelty

    gaps = (session.results.get("gaps") or {}).get("gaps", [])
    if not gaps:
        raise RuntimeError("no gaps in this session — run Gaps & Novelty first")
    yield _ev("progress", "direction", "Checking novelty against retrieved literature")
    novelty = check_novelty(session.idea, settings=settings, discovery=discovery)
    overlap = len(novelty.get("overlapping_papers", []))
    yield _ev("progress", "direction", f"{overlap} overlapping works found; deriving directions")
    directions: list[str] = []
    for g in gaps:
        directions.extend(g.get("potential_directions", []) or [])
    seen = list(dict.fromkeys(directions))[:8]
    return {
        "summary": f"{len(seen)} potential research directions",
        "directions": seen,
        "novelty": {"verdict": novelty.get("verdict"), "note": novelty.get("note")},
        "status": "ok",
    }


def _run_planner(session, settings, discovery):
    from faculty_radar.services.literature_service import search_literature
    from faculty_radar.services.planner_service import PLAN_SECTIONS, generate_plan
    from faculty_radar.services import llm_service

    yield _ev("progress", "planner", "Grounding plan in retrieved literature and gaps")
    if settings.llm.provider == "groq":
        lit = search_literature(session.idea, top_k=6, settings=settings, discovery=discovery)
        titles = [p["title"] for p in lit.get("papers", []) if p.get("title")][:6]
        gap_titles = [g["title"] for g in (session.results.get("gaps") or {}).get("gaps", [])]
        prompt = (
            f"Research idea: {session.idea}\nRetrieved papers: {titles}\n"
            f"Candidate gaps: {gap_titles}\n"
            "Draft a research plan with exactly these sections: " + ", ".join(PLAN_SECTIONS)
            + ". Ground every section in the papers/gaps above; "
              "mark anything unsupported as TODO, do not invent results."
        )
        yield _ev("progress", "planner", "Building research plan (streaming)")
        try:
            parts: list[str] = []
            for tok in llm_service.stream(prompt, settings=settings):
                parts.append(tok)
                yield _ev("token", "planner", tok)
            text = "".join(parts)
            return {
                "summary": "Research plan ready",
                "plan_text": text, "sections": PLAN_SECTIONS,
                "evidence": titles, "status": "ok",
            }
        except Exception as exc:
            yield _ev("progress", "planner", "Llama unavailable — evidence template plan assembled")
            plan = generate_plan(session.idea, settings=settings, discovery=discovery)
            plan["note"] = f"LLM unavailable: {exc}"
            return {
                "summary": "Template plan ready (LLM unavailable)",
                "plan_text": plan.get("plan_text", ""), "sections": plan.get("sections", []),
                "evidence": plan.get("evidence", []), "status": "template",
            }
    plan = generate_plan(session.idea, settings=settings, discovery=discovery)
    yield _ev("progress", "planner", "Evidence template plan assembled")
    return {
        "summary": "Template plan ready (LLM unavailable)",
        "plan_text": plan.get("plan_text", ""), "sections": plan.get("sections", []),
        "evidence": plan.get("evidence", []), "status": "template",
    }


def _run_paper(session, settings, discovery):
    plan = (session.results.get("planner") or {}).get("plan_text", "")
    gaps = (session.results.get("gaps") or {}).get("gaps", [])
    if not plan:
        raise RuntimeError("no research plan in this session — run Research Planner first")
    yield _ev("progress", "paper", "Assembling manuscript outline from plan and evidence")
    lit_papers = (session.results.get("literature") or {}).get("papers", [])
    refs = [p.get("title") for p in lit_papers[:8] if p.get("title")]
    draft = (
        f"# {session.idea}\n\n## Abstract\nTODO: summarize after experiments.\n\n"
        f"## Research Gaps\n" + "".join(f"- {g['title']}: {g['description']}\n" for g in gaps[:5])
        + "\n## References (retrieved evidence)\n" + "".join(f"- {t}\n" for t in refs)
        + "\n*IEEE formatting: export step pending formatter integration.*"
    )
    return {"summary": "Paper outline drafted from session evidence", "draft": draft, "status": "template"}


_STAGE_FNS = {
    "faculty": _run_faculty,
    "literature": _run_literature,
    "analysis": _run_analysis,
    "gaps": _run_gaps,
    "direction": _run_direction,
    "planner": _run_planner,
    "paper": _run_paper,
}
