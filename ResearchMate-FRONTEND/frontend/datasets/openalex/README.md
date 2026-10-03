# Real OpenAlex data and API response evidence

These files are separate from the original synthetic website dataset. They were obtained through the existing FastAPI backend in on-demand mode on 2026-10-03. No faculty names, papers or scores were invented for these files.

- openalex-publications-150.json: 150 distinct real publication metadata records, with provenance wrapper.
- openalex-publications-150.jsonl: the same 150 records, one per line.
- publications.json: 27 unique supporting publications from the top faculty matches returned during the captured tests.
- 01 through 07 topic JSON files: complete actual API responses for the seven requested topics.
- 08-unrelated-query.json: the captured insufficient_evidence response.
- test-report.json: query outcomes, timestamps, mode and pinned backend version.

The 150-record export includes OpenAlex IDs, titles, years, DOI links, authors, publication-associated institutions, topics and source links. It selects the first 150 lexicographically sorted unique work IDs from the live discovery cache. It is an inspection dataset, not a labeled relevance benchmark. Author and institution metadata can be incomplete or outdated; an author record does not establish faculty employment or mentor availability.

All seven topic requests returned 10 matches and verified=true in the backend response, with 50 retrieved works per request. The unrelated request returned zero matches and insufficient_evidence. These checks demonstrate successful requests and schema handling, not independently measured recommendation accuracy.

Metadata source: https://openalex.org/ . Publication text and publisher resources retain their own rights. Preserve source attribution and links. The 150-record metadata export excludes abstract text. API snapshots contain evidence excerpts returned by the backend.

The assistant does not load these files when searching. Every search calls FastAPI. Recreate snapshots using scripts/test_live_faculty_api.py with the backend running, then export the metadata using scripts/export_openalex_dataset.py. Cache files, credentials and private environment settings are not included.
