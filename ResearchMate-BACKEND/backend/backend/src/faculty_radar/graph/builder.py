"""Building the knowledge graph from normalized records.

The graph is assembled from consented faculty profiles plus the works they
authored. Node ids are prefixed (`faculty:A1`, `publication:W1001`, `topic:T100`,
`institution:I1000`) so the same input always produces the same keys.

Everything here is an observed relationship. Co-authorship edges come from
explicit authorship lists, affiliation edges from affiliation records, and
topic edges from OpenAlex topic assignments. Nothing is inferred from name
similarity, because a guessed edge would be indistinguishable from a sourced
one once it reaches a ranking.

`states_topic` edges come only from the consent registry's self-declared
expertise. OpenAlex author topics are derived from publications, so wiring them
up as stated topics would conflate derived evidence with self-report.

Submodules:
  builder  - profiles + works -> KnowledgeGraph
  queries  - traversal and co-author helpers
  store    - persistence under `paths.graph`
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import (
    EdgeType,
    FacultyProfile,
    GraphEdge,
    GraphNode,
    KnowledgeGraph,
    NodeType,
    NormalizedWork,
)
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


def faculty_node_id(faculty_id: str) -> str:
    return f"faculty:{faculty_id}"


def publication_node_id(work_id: str) -> str:
    return f"publication:{work_id}"


def topic_node_id(topic_id: str) -> str:
    return f"topic:{topic_id}"


def institution_node_id(institution_id: str) -> str:
    return f"institution:{institution_id}"


def topic_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


class GraphBuilder:
    """Accumulates nodes and edges, deduplicating as it goes."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[tuple[str, str, EdgeType], GraphEdge] = {}

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        label: str,
        *,
        attributes: dict | None = None,
    ) -> GraphNode:
        existing = self._nodes.get(node_id)
        if existing is not None:
            # Merge rather than overwrite: two profiles can contribute different
            # counts to the same person.
            if attributes:
                existing.attributes.update(attributes)
            return existing
        node = GraphNode(
            id=node_id,
            type=node_type,
            label=label,
            attributes=attributes or {},
        )
        self._nodes[node_id] = node
        return node

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: EdgeType,
        *,
        weight: float = 1.0,
        year: int | None = None,
        provenance=None,
    ) -> GraphEdge | None:
        """Add an edge, refusing endpoints that are not in the graph.

        Dropping a dangling edge keeps the graph internally consistent. This is
        the mechanism by which an unconsented person contributes no edges at
        all, even as a co-author of a consented person's work.
        """
        if source not in self._nodes or target not in self._nodes:
            logger.debug(
                "skipping edge with unknown endpoint",
                extra={"source": source, "target": target, "type": edge_type.value},
            )
            return None
        key = (source, target, edge_type)
        existing = self._edges.get(key)
        if existing is not None:
            # Keep the strongest claim when the same relationship is seen twice.
            if weight > existing.weight:
                existing.weight = weight
            return existing
        edge = GraphEdge(
            source=source,
            target=target,
            type=edge_type,
            weight=weight,
            year=year,
            provenance=provenance,
        )
        self._edges[key] = edge
        return edge

    def edge_between(
        self,
        source: str,
        target: str,
        edge_type: EdgeType | None = None,
    ) -> GraphEdge | None:
        for (edge_source, edge_target, edge_kind), edge in self._edges.items():
            if edge_source != source or edge_target != target:
                continue
            if edge_type is None or edge_kind is edge_type:
                return edge
        return None

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def add_faculty(self, profile: FacultyProfile) -> None:
        node_id = faculty_node_id(profile.faculty_id)
        self.add_node(
            node_id,
            NodeType.FACULTY,
            profile.name,
            attributes={
                "faculty_id": profile.faculty_id,
                "orcid": profile.orcid,
                "publication_count": len(profile.publications),
                "cited_by_count": profile.cited_by_count,
                "stated_topic_count": len(profile.stated_topics),
                "researcher_id": profile.researcher_id,
            },
        )
        for topic in profile.stated_topics:
            key = topic.id or topic_key(topic.name)
            topic_id = topic_node_id(key)
            self.add_node(topic_id, NodeType.TOPIC, topic.name, attributes={"stated": True})
            # Only self-declared expertise becomes `states_topic`.
            self.add_edge(
                node_id,
                topic_id,
                EdgeType.STATES_TOPIC,
                weight=topic.share,
                provenance=profile.provenance,
            )

        for institution in profile.institutions:
            key = institution.id or institution.name
            if not key:
                continue
            institution_id = institution_node_id(key)
            self.add_node(
                institution_id,
                NodeType.INSTITUTION,
                institution.name,
                attributes={
                    "ror": institution.ror,
                    "country_code": institution.country_code,
                    "type": institution.type,
                },
            )
            self.add_edge(
                node_id,
                institution_id,
                EdgeType.AT_INSTITUTION,
                provenance=profile.provenance,
            )

    def add_work(self, work: NormalizedWork, *, faculty_in_scope: set[str]) -> None:
        work_id = publication_node_id(work.openalex_id)
        is_oa = any(location.is_oa for location in work.locations)
        self.add_node(
            work_id,
            NodeType.PUBLICATION,
            work.title or work.openalex_id,
            attributes={
                "work_id": work.openalex_id,
                "year": work.year,
                "doi": work.doi,
                "cited_by_count": work.cited_by_count,
                "publication_type": work.type,
                "is_retracted": work.is_retracted,
                "is_paratext": work.is_paratext,
                "is_open_access": is_oa,
            },
        )

        # Authorship edges only for people already added to the graph.
        authored_by: set[str] = set()
        for authorship in work.authorships:
            author_id = authorship.raw_author_id
            if not author_id:
                continue
            node = faculty_node_id(author_id)
            if node not in self._nodes:
                continue
            authored_by.add(node)
            self.add_edge(
                node,
                work_id,
                EdgeType.AUTHORED,
                year=work.year,
                provenance=work.provenance,
            )
            institution = authorship.affiliation.institution
            if institution is not None:
                key = institution.id or institution.name
                if key and institution_node_id(key) in self._nodes:
                    self.add_edge(
                        node,
                        institution_node_id(key),
                        EdgeType.AT_INSTITUTION,
                        provenance=work.provenance,
                    )

        # Co-authorship is materialised from observed shared works so
        # collaboration queries do not re-derive it on every call.
        ordered = sorted(authored_by)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                self.add_edge(
                    left,
                    right,
                    EdgeType.COLLABORATED_WITH,
                    weight=1.0,
                    year=work.year,
                    provenance=work.provenance,
                )

        for topic in work.topics:
            key = topic.id or topic_key(topic.name)
            topic_id = topic_node_id(key)
            self.add_node(
                topic_id,
                NodeType.TOPIC,
                topic.name,
                attributes={
                    "topic_id": topic.id,
                    "subfield": topic.subfield,
                    "field": topic.field,
                },
            )
            self.add_edge(
                work_id,
                topic_id,
                EdgeType.ABOUT_TOPIC,
                weight=topic.share,
                provenance=work.provenance,
            )

        for keyword in work.keywords:
            keyword_id = f"keyword:{topic_key(keyword.name)}"
            self.add_node(
                keyword_id,
                NodeType.KEYWORD,
                keyword.name,
                attributes={"score": keyword.score},
            )
            self.add_edge(
                work_id,
                keyword_id,
                EdgeType.HAS_KEYWORD,
                weight=keyword.score if keyword.score is not None else 1.0,
                provenance=work.provenance,
            )

        for reference_id in work.referenced_work_ids:
            if reference_id:
                # Target may not be in scope; the referenced work is still a
                # real citation, so the edge is recorded as unresolved rather
                # than invented.
                self._edges.setdefault(
                    (work_id, publication_node_id(reference_id), EdgeType.CITES),
                    GraphEdge(
                        source=work_id,
                        target=publication_node_id(reference_id),
                        type=EdgeType.CITES,
                        weight=1.0,
                        provenance=work.provenance,
                    ),
                )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def build(self) -> KnowledgeGraph:
        # Sorting keys makes the serialized graph reproducible run to run.
        nodes = [self._nodes[key] for key in sorted(self._nodes)]
        edges = [
            self._edges[key] for key in sorted(self._edges, key=lambda k: (k[0], k[2].value, k[1]))
        ]
        graph = KnowledgeGraph(nodes={n.id: n for n in nodes}, edges=edges)
        logger.info("knowledge graph built", extra=graph_stats(graph))
        return graph


def graph_stats(graph: KnowledgeGraph) -> dict[str, int]:
    """Node and edge counts by type, for logs and `fr graph --stats`."""
    by_node: dict[str, int] = {}
    for node in graph.nodes.values():
        by_node[node.type.value] = by_node.get(node.type.value, 0) + 1
    by_edge: dict[str, int] = {}
    for edge in graph.edges:
        by_edge[edge.type.value] = by_edge.get(edge.type.value, 0) + 1
    return {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        **{f"nodes_{k}": v for k, v in sorted(by_node.items())},
        **{f"edges_{k}": v for k, v in sorted(by_edge.items())},
    }


def build_graph(
    profiles: list[FacultyProfile],
    works: list[NormalizedWork],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    store: bool = True,
) -> KnowledgeGraph:
    """Build (and optionally persist) the knowledge graph.

    Only works that at least one consented faculty member authored are
    included, and only consented faculty receive edges.
    """
    settings = settings or get_settings()
    paths = paths or build_paths(settings)

    builder = GraphBuilder()
    for profile in profiles:
        builder.add_faculty(profile)

    in_scope = {p.faculty_id for p in profiles}
    linked_work_ids = {
        publication.work_id for profile in profiles for publication in profile.publications
    }
    for work in works:
        if work.openalex_id in linked_work_ids:
            builder.add_work(work, faculty_in_scope=in_scope)

    graph = builder.build()
    if store:
        from faculty_radar.graph.store import GraphStore

        GraphStore(paths).write_graph(graph)
    return graph
