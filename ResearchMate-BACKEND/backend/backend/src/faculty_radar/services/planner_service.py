"""Research planner service (plan.md section 14).

Flow: idea -> retrieved literature -> gaps -> evidence -> LLM -> plan.
When the LLM provider is unavailable, returns an evidence-grounded template
plan with TODO markers instead of invented content.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_settings

PLAN_SECTIONS = [
    "research_question",
    "hypothesis",
    "objective",
    "dataset",
    "baseline",
    "proposed_method",
    "experiments",
    "ablation_study",
    "evaluation_metrics",
    "expected_contribution",
    "potential_risks",
]


def generate_plan(
    idea: str,
    *,
    settings: Settings | None = None,
    discovery=None,
) -> dict:
    resolved = settings or get_settings()
    q = (idea or "").strip()

    from faculty_radar.services.gap_service import detect_gaps
    from faculty_radar.services.literature_service import search_literature

    lit = search_literature(q, top_k=6, settings=resolved, discovery=discovery)
    gaps = detect_gaps(q, settings=resolved, discovery=discovery)
    evidence_titles = [p["title"] for p in lit.get("papers", []) if p.get("title")][:6]

    if resolved.llm.provider in ("groq",):
        try:
            from faculty_radar.services.llm_service import generate

            prompt = (
                f"Research idea: {q}\n"
                f"Retrieved papers: {evidence_titles}\n"
                f"Candidate gaps: {[g['title'] for g in gaps.get('gaps', [])]}\n"
                "Draft a research plan with exactly these sections: "
                + ", ".join(PLAN_SECTIONS)
                + ". Ground every section in the papers/gaps above; "
                  "mark anything unsupported as TODO, do not invent results."
            )
            text = generate(prompt, settings=resolved)["text"]
            return {
                "idea": q,
                "sections": PLAN_SECTIONS,
                "plan_text": text,
                "evidence": evidence_titles,
                "gaps": gaps.get("gaps", []),
                "status": "ok",
            }
        except Exception as exc:
            return _template_plan(q, evidence_titles, gaps, note=f"LLM unavailable: {exc}")

    return _template_plan(q, evidence_titles, gaps, note="LLM provider is extractive; template plan.")


def _template_plan(idea, evidence_titles, gaps, note: str) -> dict:
    return {
        "idea": idea,
        "sections": PLAN_SECTIONS,
        "plan_text": (
            f"# Research Plan: {idea}\n\n"
            + "\n".join(f"## {s}\nTODO: derive from evidence {evidence_titles[:3]}" for s in PLAN_SECTIONS)
        ),
        "evidence": evidence_titles,
        "gaps": gaps.get("gaps", []),
        "status": "template",
        "note": note,
    }
