"""Fixtures that let the whole pipeline run offline.

`FakeOpenAlexTransport` implements the subset of httpx's `Transport` interface
the client uses, backed by an in-memory database. This is what makes every test
hermetic: no network, no API key, no OpenAlex account, and identical results on
every machine.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from faculty_radar.config.settings import OpenAlexSettings, Settings

# --------------------------------------------------------------------------
# Sample OpenAlex payloads
# --------------------------------------------------------------------------

# Two researchers who share a surname. One has an ORCID, one does not. They are
# at *different* institutions and must never be merged - this is the case that
# naive name matching gets wrong.
AUTHORS: list[dict[str, Any]] = [
    {
        "id": "https://openalex.org/A100000001",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
        "display_name": "Wei Zhang",
        "display_name_alternatives": ["W. Zhang", "Wei L. Zhang"],
        "works_count": 4,
        "cited_by_count": 940,
        "last_known_institutions": [
            {"id": "https://openalex.org/I1000", "display_name": "Northgate University"}
        ],
        "topics": [
            {
                "id": "https://openalex.org/T100",
                "display_name": "Graph Neural Networks",
                "subfield": {"display_name": "Machine Learning"},
                "field": {"display_name": "Computer Science"},
                "score": 0.9,
            }
        ],
    },
    {
        "id": "https://openalex.org/A100000002",
        "orcid": None,
        "display_name": "Wei Zhang",
        "display_name_alternatives": [],
        "works_count": 2,
        "cited_by_count": 51,
        "last_known_institutions": [
            {
                "id": "https://openalex.org/I2000",
                "display_name": "Southport Institute of Technology",
            }
        ],
        "topics": [
            {
                "id": "https://openalex.org/T200",
                "display_name": "Marine Biology",
                "subfield": {"display_name": "Ecology"},
                "field": {"display_name": "Environmental Science"},
                "score": 0.8,
            }
        ],
    },
    {
        "id": "https://openalex.org/A100000003",
        "orcid": "https://orcid.org/0000-0001-5109-3700",
        "display_name": "Priya Raghavan",
        "display_name_alternatives": ["P. Raghavan"],
        "works_count": 3,
        "cited_by_count": 410,
        "last_known_institutions": [
            {"id": "https://openalex.org/I1000", "display_name": "Northgate University"}
        ],
        "topics": [
            {
                "id": "https://openalex.org/T300",
                "display_name": "Protein Folding",
                "subfield": {"display_name": "Biophysics"},
                "field": {"display_name": "Biology"},
                "score": 0.95,
            }
        ],
    },
    {
        "id": "https://openalex.org/A100000004",
        "orcid": None,
        "display_name": "Luis Moreno",
        "display_name_alternatives": [],
        "works_count": 2,
        "cited_by_count": 88,
        "last_known_institutions": [
            {"id": "https://openalex.org/I1000", "display_name": "Northgate University"}
        ],
        "topics": [
            {
                "id": "https://openalex.org/T100",
                "display_name": "Graph Neural Networks",
                "subfield": {"display_name": "Machine Learning"},
                "field": {"display_name": "Computer Science"},
                "score": 0.7,
            }
        ],
    },
]


def _abstract_inverted_index(text: str) -> dict[str, list[int]]:
    """Build a valid OpenAlex inverted index: token -> positions."""
    index: dict[str, list[int]] = {}
    for position, token in enumerate(text.split()):
        index.setdefault(token.strip(".,").lower(), []).append(position)
    return index


WORKS: list[dict[str, Any]] = [
    {
        "id": "https://openalex.org/W1001",
        "doi": "https://doi.org/10.1000/gnn1",
        "title": "Graph Neural Networks for Molecular Property Prediction",
        "publication_year": 2023,
        "publication_date": "2023-04-12",
        "type": "article",
        "cited_by_count": 210,
        "abstract_inverted_index": _abstract_inverted_index(
            "We present graph neural networks that learn molecular representations "
            "for property prediction. Our message passing architecture improves "
            "accuracy over baselines on three benchmark datasets."
        ),
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "raw_author_id": "https://openalex.org/A100000001",
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            },
            {
                "author_position": "middle",
                "is_corresponding": False,
                "raw_author_id": "https://openalex.org/A100000004",
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            },
        ],
        "topics": [
            {
                "id": "https://openalex.org/T100",
                "display_name": "Graph Neural Networks",
                "subfield": {"display_name": "Machine Learning"},
                "field": {"display_name": "Computer Science"},
            }
        ],
        "keywords": [
            {"id": "https://openalex.org/K1", "display_name": "graph neural network", "score": 0.9},
            {
                "id": "https://openalex.org/K2",
                "display_name": "molecular property prediction",
                "score": 0.7,
            },
        ],
        "concepts": [
            {
                "id": "https://openalex.org/C1",
                "display_name": "Artificial intelligence",
                "level": 0,
                "score": 0.9,
            }
        ],
        "referenced_works": ["https://openalex.org/W1004"],
        "related_works": ["https://openalex.org/W1005"],
        "locations": [
            {
                "landing_page_url": "https://example.org/gnn1",
                "pdf_url": "https://example.org/gnn1.pdf",
                "is_oa": True,
                "version": "publishedVersion",
                "license": "cc-by",
            }
        ],
        "is_retracted": False,
    },
    {
        "id": "https://openalex.org/W1002",
        "doi": "https://doi.org/10.1000/gnn2",
        "title": "Scaling Graph Neural Networks on Large Molecular Datasets",
        "publication_year": 2024,
        "publication_date": "2024-08-01",
        "type": "article",
        "cited_by_count": 46,
        "abstract_inverted_index": _abstract_inverted_index(
            "Scaling graph neural networks requires efficient message passing. "
            "We introduce cluster based batching that reduces memory for large "
            "molecular datasets and improves throughput."
        ),
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "raw_author_id": "https://openalex.org/A100000001",
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            },
        ],
        "topics": [
            {
                "id": "https://openalex.org/T100",
                "display_name": "Graph Neural Networks",
                "subfield": {"display_name": "Machine Learning"},
                "field": {"display_name": "Computer Science"},
            }
        ],
        "keywords": [
            {"id": "https://openalex.org/K1", "display_name": "graph neural network", "score": 0.85}
        ],
        "concepts": [],
        "referenced_works": ["https://openalex.org/W1001"],
        "related_works": [],
        "locations": [
            {
                "landing_page_url": "https://example.org/gnn2",
                "is_oa": True,
                "version": "publishedVersion",
            }
        ],
        "is_retracted": False,
    },
    {
        "id": "https://openalex.org/W1003",
        "doi": "https://doi.org/10.1000/fold1",
        "title": "Predicting Protein Folding Dynamics with Deep Learning",
        "publication_year": 2022,
        "publication_date": "2022-11-20",
        "type": "article",
        "cited_by_count": 155,
        "abstract_inverted_index": _abstract_inverted_index(
            "Protein folding dynamics remain hard to predict. We apply deep "
            "learning to molecular dynamics trajectories and predict folding "
            "rates for novel proteins."
        ),
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "raw_author_id": "https://openalex.org/A100000003",
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            },
        ],
        "topics": [
            {
                "id": "https://openalex.org/T300",
                "display_name": "Protein Folding",
                "subfield": {"display_name": "Biophysics"},
                "field": {"display_name": "Biology"},
            }
        ],
        "keywords": [
            {"id": "https://openalex.org/K3", "display_name": "protein folding", "score": 0.95}
        ],
        "concepts": [],
        "referenced_works": [],
        "related_works": [],
        "locations": [{"landing_page_url": "https://example.org/fold1", "is_oa": True}],
        "is_retracted": False,
    },
    {
        "id": "https://openalex.org/W1004",
        "doi": "https://doi.org/10.1000/marine1",
        "title": "Coral Reef Resilience Under Thermal Stress",
        "publication_year": 2021,
        "publication_date": "2021-06-05",
        "type": "article",
        "cited_by_count": 51,
        "abstract_inverted_index": _abstract_inverted_index(
            "Marine biology field surveys quantify coral reef resilience under "
            "thermal stress across reef sites."
        ),
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "raw_author_id": "https://openalex.org/A100000002",
                "raw_affiliation_strings": ["Southport Institute of Technology"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I2000",
                        "display_name": "Southport Institute of Technology",
                        "country_code": "GB",
                    }
                ],
            },
        ],
        "topics": [
            {
                "id": "https://openalex.org/T200",
                "display_name": "Marine Biology",
                "subfield": {"display_name": "Ecology"},
                "field": {"display_name": "Environmental Science"},
            }
        ],
        "keywords": [{"id": "https://openalex.org/K4", "display_name": "coral reef", "score": 0.8}],
        "concepts": [],
        "referenced_works": [],
        "related_works": [],
        "locations": [{"landing_page_url": "https://example.org/marine1", "is_oa": False}],
        "is_retracted": False,
    },
    {
        "id": "https://openalex.org/W1005",
        "doi": "https://doi.org/10.1000/gnn3",
        "title": "Interpretable Graph Neural Networks",
        "publication_year": 2025,
        "publication_date": "2025-03-14",
        "type": "article",
        "cited_by_count": 9,
        "abstract_inverted_index": _abstract_inverted_index(
            "Graph neural networks are often black boxes. We propose attribution "
            "methods that explain predictions of graph neural networks."
        ),
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "raw_author_id": "https://openalex.org/A100000001",
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            },
        ],
        "topics": [
            {
                "id": "https://openalex.org/T100",
                "display_name": "Graph Neural Networks",
                "subfield": {"display_name": "Machine Learning"},
                "field": {"display_name": "Computer Science"},
            }
        ],
        "keywords": [
            {"id": "https://openalex.org/K1", "display_name": "graph neural network", "score": 0.8}
        ],
        "concepts": [],
        "referenced_works": ["https://openalex.org/W1001"],
        "related_works": [],
        "locations": [{"landing_page_url": "https://example.org/gnn3", "is_oa": True}],
        "is_retracted": False,
    },
]

INSTITUTIONS: list[dict[str, Any]] = [
    {
        "id": "https://openalex.org/I1000",
        "display_name": "Northgate University",
        "ror": "https://ror.org/00xyz1234",
        "country_code": "US",
        "type": "education",
    },
    {
        "id": "https://openalex.org/I2000",
        "display_name": "Southport Institute of Technology",
        "ror": None,
        "country_code": "GB",
        "type": "education",
    },
]


# --------------------------------------------------------------------------
# Fake transport
# --------------------------------------------------------------------------


class FakeOpenAlexTransport(httpx.BaseTransport):
    """In-memory OpenAlex with real cursor pagination semantics.

    Records every request so tests can assert on pagination, filtering, and
    politeness parameters.
    """

    def __init__(
        self,
        institutions: list[dict] | None = None,
        authors: list[dict] | None = None,
        works: list[dict] | None = None,
        *,
        page_size: int = 2,
        failures: int = 0,
    ) -> None:
        self.institutions = institutions if institutions is not None else INSTITUTIONS
        self.authors = authors if authors is not None else AUTHORS
        self.works = works if works is not None else WORKS
        self.page_size = page_size
        self.failures_remaining = failures
        self.requests: list[httpx.Request] = []

    # -------------------------------------------------------------- internals

    @staticmethod
    def _id_of(item: dict) -> str:
        return str(item["id"]).rsplit("/", 1)[-1]

    def _page(self, items: list[dict], params: dict[str, str], key: str) -> dict:
        """Emulate OpenAlex cursor pagination over `items` keyed by `key`."""
        per_page = int(params.get("per-page", self.page_size))
        cursor = params.get("cursor")
        offset = 0 if cursor in (None, "", "*") else int(cursor)
        page = items[offset : offset + per_page]
        next_offset = offset + per_page
        return {
            "results": page,
            "meta": {
                "count": len(items),
                "page": offset // per_page + 1,
                "per_page": per_page,
                # Cursor pagination uses an opaque cursor; an empty string ends.
                "next_cursor": str(next_offset) if next_offset < len(items) else None,
                "key": key,
            },
        }

    def _filter_authors(self, params: dict[str, str]) -> list[dict]:
        raw_filter = params.get("filter", "")
        institution_id = None
        for clause in raw_filter.split(","):
            if clause.startswith("last_known_institutions.id:"):
                institution_id = clause.split(":", 1)[1].rsplit("/", 1)[-1]
        if institution_id is None:
            return list(self.authors)
        matched = [
            a
            for a in self.authors
            if any(
                str(inst.get("id", "")).rsplit("/", 1)[-1] == institution_id
                for inst in a.get("last_known_institutions", [])
            )
        ]
        return sorted(matched, key=lambda a: -a.get("cited_by_count", 0))

    def _filter_works(self, params: dict[str, str]) -> list[dict]:
        raw_filter = params.get("filter", "")
        author_id = None
        for clause in raw_filter.split(","):
            if clause.startswith("author.id:"):
                author_id = clause.split(":", 1)[1].rsplit("/", 1)[-1]
        if author_id is None:
            return list(self.works)
        matched = [
            w
            for w in self.works
            if any(
                str(a.get("raw_author_id", "")).rsplit("/", 1)[-1] == author_id
                for a in w.get("authorships", [])
            )
        ]
        return sorted(matched, key=lambda w: -(w.get("publication_year") or 0))

    # ------------------------------------------------------------ httpx API

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)

        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            return httpx.Response(503, json={"error": "temporarily unavailable"})

        path = request.url.path.strip("/")
        segments = path.split("/")
        params = dict(request.url.params)

        if path == "authors":
            return httpx.Response(
                200, json=self._page(self._filter_authors(params), params, "authors")
            )
        if path == "works":
            return httpx.Response(200, json=self._page(self._filter_works(params), params, "works"))
        if len(segments) == 2 and segments[0] == "authors":
            found = next((a for a in self.authors if self._id_of(a) == segments[1]), None)
            return (
                httpx.Response(200, json=found)
                if found
                else httpx.Response(404, json={"error": "not found"})
            )
        if len(segments) == 2 and segments[0] == "works":
            found = next((w for w in self.works if self._id_of(w) == segments[1]), None)
            return (
                httpx.Response(200, json=found)
                if found
                else httpx.Response(404, json={"error": "not found"})
            )
        if len(segments) == 2 and segments[0] == "institutions":
            found = next((i for i in self.institutions if self._id_of(i) == segments[1]), None)
            return (
                httpx.Response(200, json=found)
                if found
                else httpx.Response(404, json={"error": "not found"})
            )

        return httpx.Response(404, json={"error": f"no fake route for {path}"})


def build_fake_client(settings=None, **kwargs):
    """An OpenAlexClient wired to the fake transport, with rate limiting off.

    Accepts either a full `Settings` or an `OpenAlexSettings`.
    """
    from faculty_radar.ingestion.client import OpenAlexClient

    openalex = (
        settings.openalex if isinstance(settings, Settings) else (settings or OpenAlexSettings())
    )
    transport = kwargs.pop("transport", None) or FakeOpenAlexTransport(**kwargs)
    openalex = openalex.model_copy(
        update={"requests_per_second": 0.0, "backoff_seconds": 0.0, "max_retries": 3}
    )
    http_client = httpx.Client(transport=transport)
    client = OpenAlexClient(openalex, http_client=http_client)
    client.transport = transport  # type: ignore[attr-defined]
    return client, transport


def write_raw_snapshot(store, entity: str, payload: dict):
    """Append one payload to a RawStore and return the stored envelope."""
    store.append(entity, payload)
    return json.loads(store.read(entity)[-1])
