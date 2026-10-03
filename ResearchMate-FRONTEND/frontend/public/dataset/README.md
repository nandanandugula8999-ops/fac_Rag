# Faculty Discovery — 150-record synthetic dataset

150 publication-level records linked by faculty_id to 50 fictional faculty across 10 topics. All names, institutions, titles, abstracts and passages are synthetic; any resemblance is coincidental. This is demonstration data, not a real academic corpus or valid evidence for research claims.

## Files
- faculty-research-150.json: metadata plus records, UTF-8.
- faculty-research-150.jsonl: one record per line for ingestion.
- evaluation.json: ten topic queries evaluated against topic-based synthetic labels, not independent human judgments.

## Schema
Each record has record_id (unique publication key), faculty_id (author key), faculty_name, name_variants, designation, department, institution, stated_expertise (profile labels), inferred_expertise (publication-related labels), project, publication_title, publication_year (2021–2026), publication_type, venue, abstract, evidence_passage, research_topics, source_path, doi (null), is_synthetic (true). Arrays remain native JSON arrays. Faculty fields repeat consistently across the three publications belonging to each faculty.

## Use
Join records by faculty_id, never by name alone. source_path opens the local fictional publication; it is not a real citation. Regenerate with scripts/generate-corpus.mjs in the website source. CC0-1.0 for generated data.

## Search
The demo combines BM25 keyword ranking and cosine similarity over ten explicit, alias-normalized topic dimensions. This interpretable concept vector is not a pretrained semantic embedding model. Rank fusion combines eligible candidates, then aggregates publications by faculty. Explanations quote stored passages; no LLM is connected. Production use needs a consented real corpus, pretrained embeddings, author disambiguation and independent relevance judgments.
