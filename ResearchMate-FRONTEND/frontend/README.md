# ResearchMate · Faculty Discovery

A responsive academic discovery demo built with React 19, TypeScript, Vinext/Vite, Tailwind CSS, Radix/Shadcn components and Lucide icons. Light editorial design with real licensed photography.

## Run locally

Requires Node.js 22.13+ and npm.

```bash
npm ci
npm run dev
```

Open the local URL printed by the development server. For a Cloudflare Workers build:

```bash
npm run build
npm start
```

The Sites-hosted copy uses `.openai/hosting.json`; this identifier belongs to the original deployment. Use a new Sites project identifier for a separate deployment. Secrets are not included.

## Pages and interactions

- Landing page, discovery workspace, topic directory, publication library.
- Natural-language query input, department/topic/year/type/name filters, stated-expertise-only option, empty states and pagination.
- Faculty profiles with separate stated and publication-related expertise; publication detail and copyable synthetic citations.
- Comparison of up to three faculty; recent searches stored locally.
- Demo sign-in, guest entry, local demo workspace, demo credential reminder.
- About, data downloads, privacy and terms pages.

Demo email: `demo@faculty.test`. Demo password: `discover`.

**This is frontend demo authentication, not a secure account system. Do not enter real passwords.** No password is stored or sent to an application server. A Sites hosting access gate is separate from the demo form.

## Dataset

`public/dataset/faculty-research-150.json` contains **150 publication-level records linked to 50 fictional faculty**, three publications per faculty, across 10 research topics. JSONL is included. Every record is marked synthetic. README and evaluation results are in the same folder; a separate ZIP is downloadable from the site.

The normalized app corpus is `lib/data/corpus.json`. Regenerate deterministically:

```bash
node scripts/generate-corpus.mjs
node scripts/evaluate-search.mjs
```

No real university, person, publication, DOI, experimental result, or consent claim is represented. Names and institutions are fictional; photos are illustrative. Generated dataset: CC0-1.0.

## Retrieval implementation

`lib/search.ts` implements BM25 keyword retrieval and cosine similarity over **ten curated topic dimensions**, normalized with aliases such as NLP, LLM and IoT. Reciprocal rank fusion combines the ranked lists; faculty aggregate eligible publications using the best publication score. Explanations quote exact stored passages. Filters apply before ranking. Names resolve through known faculty IDs and explicit aliases, not fuzzy auto-merging.

This transparent baseline is **not a pretrained embedding model**, an LLM, live RAG, a web crawler or a production research recommender. Unknown topics may return no results. Natural-language understanding is limited to lexical matching and the provided topic vocabulary.

`public/dataset/evaluation.json` reports Precision@5, Recall@5 and reciprocal rank for ten queries against synthetic topic-membership labels. These labels share the corpus vocabulary and are not independent human relevance judgments; metrics are smoke checks only.

For real deployment, connect a consented academic corpus with verified IDs, real citations, secure server-side authentication, pretrained embeddings, a reranker and independently judged retrieval evaluation. Keep stated expertise separate from inferred similarity.

## Browser storage

Recent searches and optional demo display name use localStorage; compare selections and session display name use sessionStorage. The Privacy page clears all app-owned local values.

## Photography

- Mikhail Nilov / Pexels: https://www.pexels.com/photo/team-of-scientists-working-together-8851457/ (Pexels License)
- Luella Wong / Unsplash: https://unsplash.com/photos/modern-library-interior-with-curved-bookshelves-and-natural-light-y1WoXRwDBBQ (Unsplash License)

Photo subjects do not depict the fictional faculty. Their licenses remain separate from the generated dataset.

## Validation

Run `npx tsc --noEmit`, `node scripts/evaluate-search.mjs`, and `npm run build`.
The search check covers corpus keys and relations, exact evidence excerpts, ten queries, unknown query behavior, faculty names and combined filters.

## Separate live RAG backend and judge files

The existing website above remains unchanged and uses its synthetic demo dataset. A separate live API demonstration is now supplied:

- `backend/`: existing prathiksh13/fac_rag backend, pinned and preserved; see `backend/UPSTREAM.md`.
- `integration/faculty-assistant/`: separate HTML, CSS, JavaScript and FastAPI adapter. See its README for exact Windows and Linux commands.
- `datasets/openalex/`: 150 real OpenAlex publication metadata records, actual API responses and test report.
- `docs/JUDGE_GUIDE.md`: component locations, workflow, implementation status and limitations.

Start FastAPI from backend/ using `python -m uvicorn faculty_radar.api.server:app --host 127.0.0.1 --port 8000` after installing `.[demo,dev]` into a Python 3.11+ virtual environment. Start the separate frontend from the repository root using `python scripts/serve_faculty_assistant.py --port 5174`, with `VITE_API_BASE_URL=http://localhost:8000`. Open http://localhost:5174. Backend API mode must be `ondemand` for live OpenAlex discovery.

The main published website is not wired to the Python backend. The separate assistant is the live integration and only communicates with FastAPI. It does not use hardcoded faculty, publication or score fallbacks. Private environment files are excluded from Git.
