"""Stage 5 tests: graph construction, consent isolation, and traversal."""

from __future__ import annotations

import pytest

from faculty_radar.graph.builder import (
    GraphBuilder,
    build_graph,
    faculty_node_id,
    graph_stats,
    institution_node_id,
    publication_node_id,
    topic_node_id,
)
from faculty_radar.graph.queries import GraphQueries
from faculty_radar.graph.store import GraphStore
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import EdgeType, NodeType
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import build_paths
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"

WEI_NODE = faculty_node_id(WEI)
LUIS_NODE = faculty_node_id(LUIS)
PRIYA_NODE = faculty_node_id(PRIYA)
SHARED_WORK = publication_node_id("W1001")
GNN_TOPIC = topic_node_id("T100")


@pytest.fixture
def normalized():
    return normalize_authors(AUTHORS), normalize_works(WORKS)


def _consent(*ids: str, topics: dict[str, list[str]] | None = None) -> ConsentRegistry:
    entries = {}
    for rid in ids:
        entries[rid] = ConsentEntry(
            researcher_id=rid,
            consented=True,
            stated_topics=(topics or {}).get(rid, []),
        )
    return ConsentRegistry(entries, enforce=True)


def _pipeline(engine_settings, normalized, *consented, topics=None):
    authors, works = normalized
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    profiles = link_faculty(
        resolved.researchers,
        authors,
        works,
        engine_settings,
        consent=_consent(*consented, topics=topics),
        store=False,
    )
    return profiles, build_graph(profiles, works, engine_settings, store=False)


@pytest.fixture
def graph(engine_settings, normalized):
    _, built = _pipeline(engine_settings, normalized, WEI, PRIYA, LUIS)
    return built


@pytest.fixture
def queries(graph):
    return GraphQueries(graph)


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------


class TestGraphConstruction:
    def test_creates_expected_node_types(self, graph):
        types = {n.type for n in graph.nodes.values()}
        assert NodeType.FACULTY in types
        assert NodeType.PUBLICATION in types
        assert NodeType.TOPIC in types
        assert NodeType.INSTITUTION in types
        assert NodeType.KEYWORD in types

    def test_faculty_appear_as_nodes(self, graph):
        assert {WEI_NODE, PRIYA_NODE} <= set(graph.nodes)

    def test_publications_appear_as_nodes(self, graph):
        assert {publication_node_id(w) for w in ("W1001", "W1005")} <= set(graph.nodes)

    def test_authored_edges_point_from_faculty_to_publication(self, graph):
        edges = [e for e in graph.edges if e.type is EdgeType.AUTHORED]
        faculty_ids = {n.id for n in graph.nodes.values() if n.type is NodeType.FACULTY}
        assert edges
        assert all(e.source in faculty_ids for e in edges)
        assert all(e.target.startswith("publication:") for e in edges)

    def test_authored_edges_carry_year_for_temporal_queries(self, graph):
        edge = next(
            e
            for e in graph.edges
            if e.type is EdgeType.AUTHORED and e.source == WEI_NODE and e.target == SHARED_WORK
        )
        assert edge.year == 2023

    def test_collaboration_edge_from_shared_work(self, graph):
        edges = [
            e for e in graph.edges if e.type is EdgeType.COLLABORATED_WITH and e.source == WEI_NODE
        ]
        assert [e.target for e in edges] == [LUIS_NODE]

    def test_topic_edges_connect_publications_to_topics(self, graph):
        edges = [e for e in graph.edges if e.type is EdgeType.ABOUT_TOPIC]
        assert edges
        assert GNN_TOPIC in {e.target for e in edges}

    def test_institution_edges_created(self, graph):
        edges = [e for e in graph.edges if e.type is EdgeType.AT_INSTITUTION]
        assert edges
        assert all(e.target.startswith("institution:") for e in edges)

    def test_citation_edge_recorded_even_when_target_out_of_scope(self, graph):
        cites = [e for e in graph.edges if e.type is EdgeType.CITES]
        assert cites
        assert all(e.source.startswith("publication:") for e in cites)

    def test_every_resolvable_edge_endpoint_exists(self, graph):
        """Cited-but-unfetched works are the one documented exception."""
        for edge in graph.edges:
            if edge.type is EdgeType.CITES:
                continue
            assert edge.source in graph.nodes
            assert edge.target in graph.nodes

    def test_publication_node_carries_citation_metadata(self, queries):
        node = queries.node(publication_node_id("W1002"))
        assert node.attributes["year"] == 2024
        assert node.attributes["doi"]
        assert node.attributes["cited_by_count"] == 46

    def test_faculty_node_carries_publication_counts(self, queries):
        node = queries.node(WEI_NODE)
        assert node.attributes["publication_count"] == 3
        assert node.label == "Wei Zhang"

    def test_resolved_identity_is_recorded_on_faculty_node(self, queries):
        """`faculty_id` and `researcher_id` share a node; the link is an attribute."""
        node = queries.node(WEI_NODE)
        assert node.attributes["faculty_id"] == WEI
        assert node.attributes["researcher_id"] == WEI

    def test_open_access_flag_from_locations(self, queries):
        assert queries.node(SHARED_WORK).attributes["is_open_access"] is True


# --------------------------------------------------------------------------
# Consent isolation
# --------------------------------------------------------------------------


class TestConsentIsolation:
    def test_unconsented_person_is_absent(self, engine_settings, normalized):
        _, graph = _pipeline(engine_settings, normalized, WEI)
        ids = set(graph.nodes)
        assert WEI_NODE in ids
        assert PRIYA_NODE not in ids

    def test_unconsented_co_author_has_no_edges(self, engine_settings, normalized):
        _, graph = _pipeline(engine_settings, normalized, WEI)
        assert not [e for e in graph.edges if e.source == LUIS_NODE]
        assert not [e for e in graph.edges if e.target == LUIS_NODE]

    def test_unconsented_co_author_does_not_erase_shared_work(self, engine_settings, normalized):
        """W1001 is co-authored; excluding one author must keep the publication."""
        _, graph = _pipeline(engine_settings, normalized, WEI)
        assert SHARED_WORK in graph.nodes
        assert not [
            e for e in graph.edges if e.type is EdgeType.COLLABORATED_WITH and e.source == WEI_NODE
        ]

    def test_collaboration_edge_appears_only_when_both_consent(self, engine_settings, normalized):
        _, both = _pipeline(engine_settings, normalized, WEI, LUIS)
        assert [
            e
            for e in both.edges
            if e.type is EdgeType.COLLABORATED_WITH and WEI_NODE in (e.source, e.target)
        ]

        _, only_wei = _pipeline(engine_settings, normalized, WEI)
        assert not [
            e
            for e in only_wei.edges
            if e.type is EdgeType.COLLABORATED_WITH and WEI_NODE in (e.source, e.target)
        ]


# --------------------------------------------------------------------------
# Stated vs derived topics (Rule 3)
# --------------------------------------------------------------------------


class TestStatedTopicSeparation:
    def test_registry_topics_become_stated_edges(self, engine_settings, normalized):
        _, graph = _pipeline(
            engine_settings,
            normalized,
            WEI,
            topics={WEI: ["Molecular Property Prediction"]},
        )
        stated = [e for e in graph.edges if e.type is EdgeType.STATES_TOPIC]
        assert [e.source for e in stated] == [WEI_NODE]

    def test_stated_edge_carries_provenance(self, engine_settings, normalized):
        _, graph = _pipeline(
            engine_settings,
            normalized,
            WEI,
            topics={WEI: ["Molecular Property Prediction"]},
        )
        edge = next(e for e in graph.edges if e.type is EdgeType.STATES_TOPIC)
        assert edge.provenance is not None
        assert "consent_registry" in edge.provenance.source

    def test_no_stated_edges_without_registry_topics(self, engine_settings, normalized):
        _, graph = _pipeline(engine_settings, normalized, WEI, PRIYA, LUIS)
        assert not [e for e in graph.edges if e.type is EdgeType.STATES_TOPIC]

    def test_stated_topic_node_is_marked(self, engine_settings, normalized):
        _, graph = _pipeline(
            engine_settings,
            normalized,
            WEI,
            topics={WEI: ["Molecular Property Prediction"]},
        )
        node = next(
            n
            for n in graph.nodes.values()
            if n.type is NodeType.TOPIC and n.attributes.get("stated")
        )
        assert node.label == "Molecular Property Prediction"

    def test_stated_and_derived_topics_are_distinguishable(self, engine_settings, normalized):
        _, graph = _pipeline(
            engine_settings,
            normalized,
            WEI,
            PRIYA,
            LUIS,
            topics={WEI: ["Molecular Property Prediction"]},
        )
        queries = GraphQueries(graph)
        stated = queries.stated_topics_of_faculty(WEI_NODE)
        derived = queries.topics_for_faculty(WEI_NODE)
        assert [n.label for n in stated] == ["Molecular Property Prediction"]
        assert "Graph Neural Networks" in {n.label for n in derived}


# --------------------------------------------------------------------------
# Provenance and determinism
# --------------------------------------------------------------------------


class TestProvenanceAndDeterminism:
    def test_authored_edge_carries_provenance(self, queries):
        edge = queries.edge_between(WEI_NODE, SHARED_WORK, EdgeType.AUTHORED)
        assert edge.provenance is not None
        assert edge.provenance.source
        assert edge.provenance.source_url
        assert edge.provenance.record_hash

    def test_topic_edge_carries_provenance(self, queries):
        edge = queries.edge_between(SHARED_WORK, GNN_TOPIC, EdgeType.ABOUT_TOPIC)
        assert edge.provenance is not None

    def test_build_is_byte_stable_across_runs(self, engine_settings, normalized):
        _, first = _pipeline(engine_settings, normalized, WEI, PRIYA, LUIS)
        _, second = _pipeline(engine_settings, normalized, WEI, PRIYA, LUIS)

        assert list(first.nodes) == list(second.nodes)
        assert [(e.source, e.type, e.target) for e in first.edges] == [
            (e.source, e.type, e.target) for e in second.edges
        ]

    def test_nodes_written_in_sorted_order(self, graph):
        assert list(graph.nodes) == sorted(graph.nodes)

    def test_edges_sorted_for_stable_serialization(self, engine_settings, graph):
        GraphStore(build_paths(engine_settings)).write_graph(graph)
        payload = (build_paths(engine_settings).graph / "nodes.jsonl").read_text(encoding="utf-8")
        import json

        ids = [json.loads(line)["id"] for line in payload.splitlines()]
        assert ids == sorted(ids)


# --------------------------------------------------------------------------
# Traversal
# --------------------------------------------------------------------------


class TestTraversal:
    def test_works_by_returns_authored_works(self, queries):
        assert {w.id for w in queries.works_by(WEI_NODE)} == {
            publication_node_id("W1001"),
            publication_node_id("W1002"),
            publication_node_id("W1005"),
        }

    def test_authors_of_lists_co_authors(self, queries):
        assert {n.id for n in queries.authors_of(SHARED_WORK)} == {WEI_NODE, LUIS_NODE}

    def test_co_authors_counted_from_shared_work(self, queries):
        assert queries.co_authors(WEI_NODE) == {LUIS_NODE: 1}

    def test_no_co_author_without_shared_work(self, queries):
        assert queries.co_authors(PRIYA_NODE) == {}

    def test_shared_works_intersection(self, queries):
        assert queries.shared_works(WEI_NODE, LUIS_NODE) == [SHARED_WORK]

    def test_shared_works_empty_for_unconnected(self, queries):
        assert queries.shared_works(WEI_NODE, PRIYA_NODE) == []

    def test_experts_for_topic_uses_authorship_evidence(self, queries):
        experts = queries.experts_for_topic(GNN_TOPIC, min_works=1)
        ids = [n.id for n in experts]
        assert WEI_NODE in ids
        assert LUIS_NODE in ids

    def test_topic_work_counts_aggregate_authorship(self, queries):
        counts = queries.topic_work_counts(GNN_TOPIC)
        assert counts[WEI_NODE] == 3

    def test_min_works_threshold_excludes_occasional_authors(self, queries):
        experts = [n.id for n in queries.experts_for_topic(GNN_TOPIC, min_works=3)]
        assert experts == [WEI_NODE]

    def test_topics_for_faculty_aggregates_across_works(self, queries):
        assert GNN_TOPIC in {t.id for t in queries.topics_for_faculty(WEI_NODE)}

    def test_institutions_for_faculty(self, queries):
        found = queries.institutions_for_faculty(WEI_NODE)
        assert found
        assert all(n.type is NodeType.INSTITUTION for n in found)

    def test_citations_and_cited_by(self, queries):
        cites = queries.citations(publication_node_id("W1002"))
        assert publication_node_id("W1001") in cites
        assert queries.cited_by(publication_node_id("W1001"))

    def test_shortest_path_faculty_to_topic(self, queries):
        assert queries.shortest_path(WEI_NODE, GNN_TOPIC) == [
            WEI_NODE,
            SHARED_WORK,
            GNN_TOPIC,
        ]

    def test_shortest_path_none_when_topic_unrelated(self, queries):
        assert queries.shortest_path(PRIYA_NODE, GNN_TOPIC) is None

    def test_shortest_path_to_self(self, queries):
        assert queries.shortest_path(WEI_NODE, WEI_NODE) == [WEI_NODE]

    def test_shortest_path_unknown_node(self, queries):
        assert queries.shortest_path("faculty:nope", WEI_NODE) is None

    def test_neighbors_sorted(self, queries):
        ids = [n.id for n in queries.neighbors(WEI_NODE)]
        assert ids == sorted(ids)

    def test_degree_counts_in_and_out(self, queries):
        # Wei: 3 authored (out) + 1 collaboration (out) + 1 institution (in).
        expected = (
            len(queries.works_by(WEI_NODE))
            + len(queries.outgoing(WEI_NODE, EdgeType.COLLABORATED_WITH))
            + len(queries.institutions_for_faculty(WEI_NODE))
        )
        assert queries.degree_of(WEI_NODE) == expected

    def test_nodes_of_type(self, queries):
        assert all(n.type is NodeType.FACULTY for n in queries.nodes_of_type(NodeType.FACULTY))

    def test_stats_counts_by_type(self, graph):
        stats = graph_stats(graph)
        assert stats["nodes"] == len(graph.nodes)
        assert stats["edges"] == len(graph.edges)
        assert stats["nodes_faculty"] == 3
        assert stats["edges_authored"] > 0

    def test_empty_graph_queries_are_safe(self):
        queries = GraphQueries()
        assert queries.co_authors("faculty:missing") == {}
        assert queries.works_by("faculty:missing") == []
        assert queries.stats() == {"nodes": 0, "edges": 0}


# --------------------------------------------------------------------------
# Builder invariants
# --------------------------------------------------------------------------


class TestBuilderInvariants:
    def test_duplicate_nodes_merge_attributes(self):
        builder = GraphBuilder()
        first = builder.add_node("faculty:A", NodeType.FACULTY, "A", attributes={"x": 1})
        second = builder.add_node("faculty:A", NodeType.FACULTY, "A", attributes={"y": 2})

        assert first is second
        graph = builder.build()
        assert graph_stats(graph)["nodes"] == 1
        assert graph.nodes["faculty:A"].attributes == {"x": 1, "y": 2}

    def test_duplicate_edges_collapse(self):
        builder = GraphBuilder()
        builder.add_node("faculty:A", NodeType.FACULTY, "A")
        builder.add_node("faculty:B", NodeType.FACULTY, "B")
        builder.add_edge("faculty:A", "faculty:B", EdgeType.COLLABORATED_WITH)
        builder.add_edge("faculty:A", "faculty:B", EdgeType.COLLABORATED_WITH)

        assert graph_stats(builder.build())["edges"] == 1

    def test_edge_with_unknown_endpoint_dropped(self):
        builder = GraphBuilder()
        builder.add_node("faculty:A", NodeType.FACULTY, "A")

        assert builder.add_edge("faculty:A", "faculty:missing", EdgeType.AUTHORED) is None
        assert graph_stats(builder.build())["edges"] == 0

    def test_strongest_weight_retained_for_repeated_edge(self):
        builder = GraphBuilder()
        builder.add_node("faculty:A", NodeType.FACULTY, "A")
        builder.add_node("publication:W", NodeType.PUBLICATION, "W")
        builder.add_edge("faculty:A", "publication:W", EdgeType.AUTHORED, weight=0.2)
        builder.add_edge("faculty:A", "publication:W", EdgeType.AUTHORED, weight=0.9)

        assert builder.build().edges[0].weight == 0.9

    def test_edge_key_lookup_helpers(self):
        builder = GraphBuilder()
        builder.add_node("faculty:A", NodeType.FACULTY, "A")
        builder.add_node("publication:W", NodeType.PUBLICATION, "W")
        builder.add_edge("faculty:A", "publication:W", EdgeType.AUTHORED)

        assert builder.edge_between("faculty:A", "publication:W") is not None
        assert builder.edge_between("faculty:A", "publication:W", EdgeType.CITES) is None
        assert builder.edge_between("faculty:A", "publication:other") is None

    def test_topic_node_id_uses_slug_for_nameless_topics(self):
        from faculty_radar.graph.builder import topic_key

        assert topic_key("Graph Neural Networks") == "graph_neural_networks"
        assert topic_node_id(topic_key("Graph Neural Networks")) == "topic:graph_neural_networks"

    def test_institution_node_id_helper(self):
        assert institution_node_id("I1000") == "institution:I1000"


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class TestGraphStore:
    def test_roundtrip_preserves_graph(self, engine_settings, graph):
        paths = build_paths(engine_settings)
        GraphStore(paths).write_graph(graph)

        loaded = GraphStore(paths).load_graph()
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)

    def test_jsonl_sidecars_written(self, engine_settings, graph):
        paths = build_paths(engine_settings)
        GraphStore(paths).write_graph(graph)

        assert paths.graph.joinpath("nodes.jsonl").exists()
        assert paths.graph.joinpath("edges.jsonl").exists()

    def test_load_queries_is_usable(self, engine_settings, graph):
        paths = build_paths(engine_settings)
        GraphStore(paths).write_graph(graph)

        queries = GraphStore(paths).load_queries()
        assert len(queries.works_by(WEI_NODE)) == 3
        assert queries.co_authors(WEI_NODE) == {LUIS_NODE: 1}

    def test_meta_reports_counts(self, engine_settings, graph):
        paths = build_paths(engine_settings)
        GraphStore(paths).write_graph(graph)

        meta = GraphStore(paths).load_meta()
        assert meta["nodes"] == len(graph.nodes)
        assert meta["edges"] == len(graph.edges)

    def test_missing_graph_returns_empty(self, engine_settings):
        assert GraphStore(build_paths(engine_settings)).load_graph().nodes == {}

    def test_missing_graph_queries_are_safe(self, engine_settings):
        assert GraphStore(build_paths(engine_settings)).load_queries().works_by(WEI_NODE) == []

    def test_rewrite_replaces_previous_content(self, engine_settings, graph):
        paths = build_paths(engine_settings)
        store = GraphStore(paths)
        store.write_graph(graph)
        store.write_graph(graph)

        loaded = store.load_graph()
        assert len(loaded.edges) == len(graph.edges)
