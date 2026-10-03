# ResearchMate: code and demonstration guide

ResearchMate helps students identify researchers relevant to a topic and inspect the publications and passages behind each match.

## What is complete

- The original React/TypeScript website and its styling are preserved. It still uses its explicitly synthetic demonstration corpus.
- The existing Faculty Radar RAG backend is imported from prathiksh13/fac_rag without rewriting its algorithms.
- A separate HTML/CSS/JavaScript Faculty Assistant calls that backend and renders its actual responses. It does not load saved results as fallback data.
- Real OpenAlex publication metadata and actual API response snapshots are supplied separately for inspection.

The published website is not connected to this backend. Run the separate assistant locally for the live RAG demonstration. Python FastAPI needs its own deployment for a public hosted integration.

## Files to show a judge

| Part | Location | Purpose |
| --- | --- | --- |
| Separate HTML | integration/faculty-assistant/index.html | Query form, loading/error and result containers |
| Separate CSS | integration/faculty-assistant/styles.css | Styling for the separate demonstration |
| Separate JavaScript | integration/faculty-assistant/app.js | Render actual API results and evidence |
| API adapter | integration/faculty-assistant/api.js | POST query and top_k to FastAPI; validate responses |
| Original website | components/experience.tsx and app/globals.css | Existing React UI and styles |
| RAG source | backend/src/faculty_radar/ | Unchanged discovery, retrieval, ranking and verification code |
| API server | backend/src/faculty_radar/api/server.py | FastAPI search endpoint and health route |
| Backend provenance | backend/UPSTREAM.md and UPSTREAM_MANIFEST.json | Pinned source and byte-preservation manifest |
| Real dataset | datasets/openalex/openalex-publications-150.json and .jsonl | 150 real publication metadata records |
| Live test evidence | datasets/openalex/test-report.json | Results of seven topics and unrelated query |
| Synthetic dataset | public/dataset/ | Original, clearly labeled website demonstration data |

## Explain the flow

A student enters a topic. The browser posts it to FastAPI. The existing backend searches OpenAlex, resolves authors, builds a temporary corpus, combines keyword and vector retrieval, reranks, selects evidence, scores expertise, generates an extractive answer, and verifies citations and quotes. The browser displays the returned researchers, scores, papers and passages.

The browser only talks to FastAPI. It does not call OpenAlex or implement RAG. Crossref metadata checks are also performed inside the existing backend.

## Honest interpretation

A relevance score is the backend's ranking value, not a probability or a guaranteed accuracy percentage. Citation/quote verification means the backend's checks passed, not that every scientific conclusion is true or the researcher is available as a mentor. OpenAlex authors can include researchers outside faculty roles, and their institutions are publication metadata rather than guaranteed current employment.

The default backend uses hashing vectors and extractive generation; it does not require a paid generative LLM or a trained neural embedding model. Optional neural embedding support belongs to the upstream project.

The uploaded configuration has no institution restriction, so the tested mode searches globally. Stated expertise is shown only when returned; live discovery commonly supplies publication-derived expertise. The upstream on-demand path assumes in-scope authors are consented; it is not evidence of individual consent. An institution deployment needs a real scope and consent policy. These rules were not modified in this import.

Semantic Scholar, Firebase storage, personalized feedback and advanced NLP blocks in the concept diagram are future/optional items, not claims of implemented features.

## Demonstration

Follow ../integration/faculty-assistant/README.md. Start the backend and the separate assistant in two terminals. Open http://localhost:5174 and search machine learning, computer vision, cybersecurity, quantum computing, natural language processing, robotics and graph neural networks. Expand the raw API response to inspect provenance and claims.

Try `zzzxqvpl nonexistent purple teapot faculty topic 94721` for the captured insufficient-evidence case. An ordinary unrelated topic may legitimately have papers; lack of evidence is determined by the backend. Network failures must be investigated rather than interpreted as proof no researcher exists.
