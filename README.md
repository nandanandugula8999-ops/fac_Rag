# ResearchMate — Research AI Platform

ResearchMate evolves the **Faculty Discovery (PS23 core)** assistant into a complete
**Research AI** workspace:

**Research Idea → Faculty Discovery → Literature Search → Paper Analysis →
Research Gaps → Research Direction → Research Planner → Paper Studio → IEEE Format**

Core principle: **retrieval → evidence → LLM reasoning → grounded output.**
The LLM never fabricates papers, faculty, citations, gaps, or statistics —
unsupported claims return explicit `insufficient_evidence` instead of guesses.

## Repository layout

```
fac_rag/
├── plan(4).md                  MASTER SPECIFICATION (read first)
├── README.md                  this file
├── ResearchMate-BACKEND/
│   ├── .venv/                 Python virtualenv (gitignored)
│   └── backend/backend/       FastAPI + research engine (faculty_radar)
└── ResearchMate-FRONTEND/
    └── frontend/              Vinext/Next + shadcn UI
```

## Backend — run

From `ResearchMate-BACKEND/backend/backend`:

```powershell
$env:PYTHONPATH = "src"
& "..\..\.venv\Scripts\python.exe" -m uvicorn faculty_radar.api.server:app --port 8000
```

- Health: `http://127.0.0.1:8000/health` · Docs: `http://127.0.0.1:8000/docs`
- Modes via `FACULTY_API_MODE`: `ondemand` (default, live OpenAlex) | `corpus` | `fixture`
- Server-side only env (in backend `.env`, never in frontend):
  `FR_GROQ__API_KEY`, `FR_GROQ__MODEL`, `FR_LLM__PROVIDER=groq`

Key endpoints: `/api/faculty/search`, `/api/papers/search`, `/api/papers/{id}`,
`/api/analysis/gaps`, `/api/analysis/novelty`, `/api/planner/generate`,
`/api/projects`, `/api/sessions` (+ `/run` SSE progress, `/papers`, `/assist`),
`/api/ai/providers`.

## Frontend — run

From `ResearchMate-FRONTEND/frontend`:

```powershell
npm install
$env:NEXT_PUBLIC_BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

Main routes: `/app` (Dashboard workspace), `/faculty`, `/literature`, `/analysis`,
`/gaps`, `/planner`, `/paper-studio`, `/projects`, `/saved`, `/drafts`,
`/history`, `/analytics`, `/collections`, `/documents`, `/settings`.
The classic demo corpus stays at `/discover`.

## Product rules (enforced)

- Faculty Discovery + Faculty RAG stay extractive and offline-capable.
- All Research AI reasoning flows `Frontend → Backend → Unified LLM Service → Groq → Llama`.
- No `VITE_GROQ_API_KEY` / `NEXT_PUBLIC_GROQ_API_KEY` anywhere.
- No fake data: empty states instead of invented content; dataset limits stated openly.
- Manual navigation only — the app never auto-redirects between stages.

## Known limitations

- The Groq account currently exposes no Llama chat model (both Llama IDs 404);
  LLM prose degrades honestly until `FR_GROQ__MODEL` points to an accessible model
  (`openai/gpt-oss-20b` verified working on this key).
- No IEEE DOCX formatter exists in the repo yet — Studio marks export as pending.
- Projects/sessions persist in-process (Firestore wiring is future work).
