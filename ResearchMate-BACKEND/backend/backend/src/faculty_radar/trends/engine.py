"""Topic and keyword trend analysis over publication time windows.

The present is the newest publication year in the snapshot, not the wall
clock: trends must be reproducible from the same data on any date. Both topics
and keywords get the same treatment, since an emerging method often shows up
as a keyword before OpenAlex assigns it a topic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import (
    FacultyProfile,
    NormalizedWork,
    Status,
    TopicTrend,
    TrendReport,
)

logger = get_logger(__name__)

DIRECTIONS = ("rising", "declining", "stable", "emerging")


@dataclass
class TrendEngine:
    """Compares recent vs baseline publication rates per topic/keyword."""

    works: list[NormalizedWork]
    profiles: list[FacultyProfile] = field(default_factory=list)
    settings: Settings | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()

    def analyze(self) -> TrendReport:
        """Build the trend report for the configured windows."""
        settings = self.settings or get_settings()
        dated = [w for w in self.works if w.year is not None]
        undated = len(self.works) - len(dated)
        if not dated:
            return TrendReport(
                status=Status.INSUFFICIENT_EVIDENCE,
                notes=["no dated publications; trends need timestamps"],
            )

        present = max(w.year for w in dated if w.year is not None)
        recent_years = set(range(present - settings.trends.recent_years + 1, present + 1))
        baseline_years = set(
            range(
                present - settings.trends.recent_years - settings.trends.baseline_years + 1,
                present - settings.trends.recent_years + 1,
            )
        )
        faculty_by_work = _faculty_by_work(self.profiles)

        topics = self._analyze_terms(
            dated, recent_years, baseline_years, settings, faculty_by_work, kind="topic"
        )
        keywords = self._analyze_terms(
            dated, recent_years, baseline_years, settings, faculty_by_work, kind="keyword"
        )
        year_counts = Counter(str(w.year) for w in dated)
        notes = [
            f"recent window {min(recent_years)}-{max(recent_years)}, "
            f"baseline window {min(baseline_years)}-{max(baseline_years)}"
        ]
        if undated:
            notes.append(f"excluded {undated} undated publication(s) from window math")
        report = TrendReport(
            year_counts=dict(sorted(year_counts.items())),
            topics=topics,
            keywords=keywords,
            recent_years=settings.trends.recent_years,
            baseline_years=settings.trends.baseline_years,
            notes=notes,
            status=Status.OK,
        )
        logger.debug(
            "trend analysis complete",
            extra={"topics": len(topics), "keywords": len(keywords)},
        )
        return report

    def _analyze_terms(
        self, works, recent_years, baseline_years, settings, faculty_by_work, *, kind: str
    ) -> list[TopicTrend]:
        terms: dict[str, dict] = {}
        for work in works:
            items = work.topics if kind == "topic" else work.keywords
            for item in items:
                entry = terms.setdefault(
                    item.key,
                    {
                        "name": item.name,
                        "field": getattr(item, "field", None),
                        "fields": Counter(),
                        "years": Counter(),
                        "faculty": set(),
                    },
                )
                entry["years"][work.year] += 1
                if getattr(item, "field", None):
                    entry["fields"][item.field] += 1
                entry["faculty"].update(faculty_by_work.get(work.openalex_id, ()))

        trends: list[TopicTrend] = []
        for key in sorted(terms):
            entry = terms[key]
            total = sum(entry["years"].values())
            if total < settings.trends.min_publications:
                continue
            recent = sum(count for year, count in entry["years"].items() if year in recent_years)
            baseline = sum(
                count for year, count in entry["years"].items() if year in baseline_years
            )
            recent_rate = recent / settings.trends.recent_years
            baseline_rate = baseline / settings.trends.baseline_years
            if baseline_rate > 0:
                growth = recent_rate / baseline_rate
            elif recent > 0:
                # New to the baseline window: report recent volume, not infinity.
                growth = float(recent)
            else:
                growth = 0.0

            if baseline == 0 and recent >= settings.trends.min_recent_publications:
                direction = "emerging"
            elif (
                growth >= settings.trends.emerging_growth_ratio
                and recent >= settings.trends.min_recent_publications
            ):
                direction = "rising"
            elif growth <= 1 / settings.trends.emerging_growth_ratio and baseline > 0:
                direction = "declining"
            else:
                direction = "stable"

            years = sorted(entry["years"])
            field = entry["fields"].most_common(1)
            trends.append(
                TopicTrend(
                    topic=entry["name"],
                    field=field[0][0] if field else None,
                    total_publications=total,
                    recent_publications=recent,
                    baseline_publications=baseline,
                    growth_ratio=growth,
                    first_year=years[0] if years else None,
                    last_year=years[-1] if years else None,
                    faculty_ids=sorted(entry["faculty"]),
                    direction=direction,
                    sample_years=years,
                    counts_by_year={str(y): entry["years"][y] for y in years},
                    notes=[f"{direction}: {recent} recent vs {baseline} baseline"],
                )
            )
        trends.sort(key=lambda t: (-t.growth_ratio, t.topic))
        return trends


def _faculty_by_work(profiles: list[FacultyProfile]) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for profile in profiles:
        for publication in profile.publications:
            mapping.setdefault(publication.work_id, set()).add(profile.faculty_id)
    return mapping


def analyze_trends(
    works: list[NormalizedWork],
    profiles: list[FacultyProfile] | None = None,
    settings: Settings | None = None,
) -> TrendReport:
    """Convenience entry point for trend analysis."""
    return TrendEngine(works, profiles or [], settings).analyze()
