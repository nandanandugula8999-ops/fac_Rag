"""Knowledge graph persistence.

Writes to `data/graph/`:
  knowledge_graph.json  single document with `meta`, `nodes`, `edges`
  nodes.jsonl           one node per line
  edges.jsonl           one edge per line

Writes go through a temporary file and an atomic replace so a crashed run
cannot leave a half-written graph behind.
"""

from __future__ import annotations

import json
from pathlib import Path

from faculty_radar.config import get_logger
from faculty_radar.graph.builder import graph_stats
from faculty_radar.graph.queries import GraphQueries
from faculty_radar.models import GraphEdge, GraphNode, KnowledgeGraph
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


class GraphStore:
    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = paths or build_paths()

    @property
    def graph_path(self) -> Path:
        return self.paths.graph / "knowledge_graph.json"

    @property
    def nodes_path(self) -> Path:
        return self.paths.graph / "nodes.jsonl"

    @property
    def edges_path(self) -> Path:
        return self.paths.graph / "edges.jsonl"

    def write_graph(self, graph: KnowledgeGraph) -> Path:
        self.paths.ensure()
        nodes = [graph.nodes[key] for key in sorted(graph.nodes)]
        edges = sorted(graph.edges, key=lambda e: (e.source, e.type.value, e.target))

        payload = {
            "meta": graph_stats(graph),
            "nodes": [n.model_dump(mode="json") for n in nodes],
            "edges": [e.model_dump(mode="json") for e in edges],
        }
        self._atomic_write_json(self.graph_path, payload)
        self._atomic_write_jsonl(self.nodes_path, [n.model_dump(mode="json") for n in nodes])
        self._atomic_write_jsonl(self.edges_path, [e.model_dump(mode="json") for e in edges])
        logger.info("knowledge graph written", extra={"path": str(self.graph_path)})
        return self.graph_path

    def load_graph(self) -> KnowledgeGraph:
        if not self.graph_path.exists():
            logger.warning(
                "no knowledge graph found; returning empty graph",
                extra={"path": str(self.graph_path)},
            )
            return KnowledgeGraph(nodes={}, edges=[])
        payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        return KnowledgeGraph(
            nodes={node["id"]: GraphNode.model_validate(node) for node in payload.get("nodes", [])},
            edges=[GraphEdge.model_validate(edge) for edge in payload.get("edges", [])],
        )

    def load_queries(self) -> GraphQueries:
        return GraphQueries(self.load_graph())

    def load_meta(self) -> dict:
        if not self.graph_path.exists():
            return {}
        payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        return payload.get("meta", {})

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @staticmethod
    def _atomic_write_jsonl(path: Path, records: list[dict]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        tmp.replace(path)
        return path
