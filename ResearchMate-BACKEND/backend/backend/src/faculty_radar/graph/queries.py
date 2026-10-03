"""Graph traversal helpers.

Read-only queries over a built graph. These are what make the graph load-bearing
rather than decorative: expert-for-topic search, co-author detection, and
explainable paths between a person and a topic all start here, so a ranking can
always cite the structural evidence behind it.

Co-authorship queries count only shared works. Topic similarity is never used as
a collaboration signal here - collaboration evidence is authorship evidence.
"""

from __future__ import annotations

from collections.abc import Iterable

from faculty_radar.graph.builder import graph_stats
from faculty_radar.models import EdgeType, GraphEdge, KnowledgeGraph, NodeType

DEFAULT_MAX_DEPTH = 4


class GraphQueries:
    """Read-only traversal over a `KnowledgeGraph`."""

    def __init__(self, graph: KnowledgeGraph | None = None) -> None:
        self.graph = graph if graph is not None else KnowledgeGraph(nodes={}, edges=[])
        self._out: dict[str, list[GraphEdge]] = {}
        self._in: dict[str, list[GraphEdge]] = {}
        for edge in self.graph.edges:
            self._out.setdefault(edge.source, []).append(edge)
            self._in.setdefault(edge.target, []).append(edge)
        # Sorted adjacency keeps every traversal deterministic.
        for bucket in (self._out, self._in):
            for key in bucket:
                bucket[key].sort(key=lambda e: (e.target, e.type.value))

    @classmethod
    def from_parts(
        cls,
        nodes: dict,
        edges: list[GraphEdge],
    ) -> GraphQueries:
        return cls(KnowledgeGraph(nodes=dict(nodes), edges=list(edges)))

    # ------------------------------------------------------------------
    # Basic access
    # ------------------------------------------------------------------

    def node(self, node_id: str):
        return self.graph.nodes.get(node_id)

    def node_ids(self) -> set[str]:
        return set(self.graph.nodes)

    def nodes_of_type(self, node_type: NodeType) -> list:
        return sorted(
            (n for n in self.graph.nodes.values() if n.type is node_type),
            key=lambda n: n.id,
        )

    def outgoing(self, node_id: str, edge_type: EdgeType | None = None) -> list[GraphEdge]:
        edges = self._out.get(node_id, [])
        return [e for e in edges if edge_type is None or e.type is edge_type]

    def incoming(self, node_id: str, edge_type: EdgeType | None = None) -> list[GraphEdge]:
        edges = self._in.get(node_id, [])
        return [e for e in edges if edge_type is None or e.type is edge_type]

    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list:
        found: dict[str, object] = {}
        for edge in self.outgoing(node_id, edge_type):
            node = self.graph.nodes.get(edge.target)
            if node is not None:
                found[node.id] = node
        return sorted(found.values(), key=lambda n: n.id)

    def edge_between(
        self,
        source: str,
        target: str,
        edge_type: EdgeType | None = None,
    ) -> GraphEdge | None:
        for edge in self._out.get(source, []):
            if edge.target == target and (edge_type is None or edge.type is edge_type):
                return edge
        return None

    # ------------------------------------------------------------------
    # Domain traversals
    # ------------------------------------------------------------------

    def faculty_ids(self) -> set[str]:
        return {n.id for n in self.graph.nodes.values() if n.type is NodeType.FACULTY}

    def works_by(self, faculty_id: str) -> list:
        return self.neighbors(faculty_id, EdgeType.AUTHORED)

    def authors_of(self, work_id: str) -> list:
        return [
            self.graph.nodes[e.source]
            for e in self.incoming(work_id, EdgeType.AUTHORED)
            if e.source in self.graph.nodes
        ]

    def topics_of_work(self, work_id: str) -> list:
        return self.neighbors(work_id, EdgeType.ABOUT_TOPIC)

    def keywords_of_work(self, work_id: str) -> list:
        return self.neighbors(work_id, EdgeType.HAS_KEYWORD)

    def topics_for_faculty(self, faculty_id: str) -> list:
        """Topics reachable through that person's authored works."""
        found: dict[str, object] = {}
        for work in self.works_by(faculty_id):
            for topic in self.topics_of_work(work.id):
                found[topic.id] = topic
        return sorted(found.values(), key=lambda n: n.id)

    def stated_topics_of_faculty(self, faculty_id: str) -> list:
        return self.neighbors(faculty_id, EdgeType.STATES_TOPIC)

    def institutions_for_faculty(self, faculty_id: str) -> list:
        return self.neighbors(faculty_id, EdgeType.AT_INSTITUTION)

    def experts_for_topic(
        self,
        topic_id: str,
        min_works: int = 1,
    ) -> list:
        """People with at least `min_works` authored works about a topic.

        Authorship is an observed fact, so this is stronger evidence than
        embedding similarity between a profile text and a query.
        """
        counts: dict[str, int] = {}
        for edge in self.incoming(topic_id, EdgeType.ABOUT_TOPIC):
            for authorship in self.incoming(edge.source, EdgeType.AUTHORED):
                if authorship.source in self.faculty_ids():
                    counts[authorship.source] = counts.get(authorship.source, 0) + 1
        return sorted(
            (self.graph.nodes[node_id] for node_id, count in counts.items() if count >= min_works),
            key=lambda n: (-counts[n.id], n.id),
        )

    def topic_work_counts(self, topic_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in self.incoming(topic_id, EdgeType.ABOUT_TOPIC):
            for authorship in self.incoming(edge.source, EdgeType.AUTHORED):
                if authorship.source in self.faculty_ids():
                    counts[authorship.source] = counts.get(authorship.source, 0) + 1
        return counts

    def co_authors(self, faculty_id: str) -> dict[str, int]:
        """People sharing at least one authored work, mapped to that count."""
        shared: dict[str, set[str]] = {}
        for work in self.works_by(faculty_id):
            for edge in self.incoming(work.id, EdgeType.AUTHORED):
                if edge.source != faculty_id and edge.source in self.faculty_ids():
                    shared.setdefault(edge.source, set()).add(work.id)
        return {node_id: len(ids) for node_id, ids in sorted(shared.items())}

    def shared_works(self, left: str, right: str) -> list[str]:
        left_works = {w.id for w in self.works_by(left)}
        right_works = {w.id for w in self.works_by(right)}
        return sorted(left_works & right_works)

    def citations(self, work_id: str) -> list[str]:
        return [e.target for e in self.outgoing(work_id, EdgeType.CITES)]

    def cited_by(self, work_id: str) -> list[str]:
        return [e.source for e in self.incoming(work_id, EdgeType.CITES)]

    # ------------------------------------------------------------------
    # Explainability
    # ------------------------------------------------------------------

    def shortest_path(
        self,
        source: str,
        target: str,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> list[str] | None:
        """Breadth-first node-id path, or None when disconnected.

        The path from a person to a topic is the reason a topic was attributed
        to them, which is what makes an expertise claim checkable.
        """
        if source not in self.graph.nodes or target not in self.graph.nodes:
            return None
        if source == target:
            return [source]

        seen = {source}
        frontier: list[tuple[str, list[str]]] = [(source, [source])]
        for _ in range(max_depth):
            next_frontier: list[tuple[str, list[str]]] = []
            for node_id, path in frontier:
                for edge in self.outgoing(node_id):
                    if edge.target in seen:
                        continue
                    extended = [*path, edge.target]
                    if edge.target == target:
                        return extended
                    seen.add(edge.target)
                    next_frontier.append((edge.target, extended))
            frontier = next_frontier
            if not frontier:
                break
        return None

    def degree_of(self, node_id: str) -> int:
        return len(self._out.get(node_id, [])) + len(self._in.get(node_id, []))

    def degrees(self) -> dict[str, int]:
        counts = dict.fromkeys(self.graph.nodes, 0)
        for edge in self.graph.edges:
            counts[edge.source] = counts.get(edge.source, 0) + 1
            counts[edge.target] = counts.get(edge.target, 0) + 1
        return counts

    def edges_of_type(self, edge_type: EdgeType) -> list[GraphEdge]:
        return self.graph.edges_of(edge_type)

    def edges_among(self, edge_types: Iterable[EdgeType]) -> list[GraphEdge]:
        wanted = set(edge_types)
        return [e for e in self.graph.edges if e.type in wanted]

    def stats(self) -> dict[str, int]:
        return graph_stats(self.graph)
