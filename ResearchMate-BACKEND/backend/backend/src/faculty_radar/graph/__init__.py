"""Knowledge graph construction.

Stage 5 of the pipeline. Builds the graph the whole system reasons over:

    Institution --employs--> Person --authored--> Work --about--> Topic
                                        |
                                        +--affiliated_with--> Institution

Node types: `person`, `work`, `topic`, `institution`.
Edge types: `authored`, `affiliated_with`, `about`, `employs`, `cites`,
`co_authored`.

The graph is not decoration. Collaboration detection, co-author traversal,
trend propagation, and expert-for-topic queries all run over these edges, which
is what keeps the system grounded in structure instead of embedding similarity.

Two properties are enforced at build time:

  * every node and edge is deterministic and reproducible from the same inputs
  * no edge is invented - each carries the provenance of the record that
    supports it, so a traversal can always be traced back to source data

Submodules:
  builder  - profiles + works + topics + institutions -> KnowledgeGraph
  queries  - neighbourhood and co-author traversal helpers
  store    - JSON and JSONL persistence under `paths.graph`
"""

from faculty_radar.graph.builder import GraphBuilder, build_graph
from faculty_radar.graph.queries import GraphQueries
from faculty_radar.graph.store import GraphStore

__all__ = [
    "GraphBuilder",
    "GraphQueries",
    "GraphStore",
    "build_graph",
]
