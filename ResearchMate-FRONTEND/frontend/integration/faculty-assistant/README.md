# Separate live Faculty Assistant

This plain HTML/CSS/JavaScript page demonstrates the imported backend without changing the existing ResearchMate website. It displays actual FastAPI responses and rejects fixture mode. Saved datasets are never loaded as substitute search results.

## Requirements

Python 3.11 or newer. Git. Internet access for OpenAlex/Crossref. Run commands from the cloned ResearchMate repository unless instructed otherwise.

## Backend: Windows PowerShell

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[demo,dev]"
Copy-Item .env.example .env
$env:FACULTY_API_MODE = "ondemand"
.\.venv\Scripts\python.exe -m uvicorn faculty_radar.api.server:app --host 127.0.0.1 --port 8000
```

If you already have the faculty-provided environment file, place it at backend/.env instead of replacing it with the template. Edit FR_OPENALEX__MAILTO to your real contact email if required by your configuration. Keep backend settings private. No frontend secret is needed.

## Backend: macOS/Linux

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[demo,dev]'
cp .env.example .env
FACULTY_API_MODE=ondemand .venv/bin/python -m uvicorn faculty_radar.api.server:app --host 127.0.0.1 --port 8000
```

Use the provided private configuration instead of the cp command when available. Run from backend/ so the existing source can locate its tests module and configuration. Open http://localhost:8000/docs to inspect the API, or http://localhost:8000/health to confirm mode=ondemand and corpus_source=live-openalex.

## Separate frontend: second terminal, repository root

Windows PowerShell:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000"
py -3 scripts/serve_faculty_assistant.py --port 5174
```

macOS/Linux:

```bash
VITE_API_BASE_URL=http://localhost:8000 python3 scripts/serve_faculty_assistant.py --port 5174
```

Open http://localhost:5174. Alternatively copy integration/faculty-assistant/.env.example to .env in the same folder and edit VITE_API_BASE_URL. This standard-library server reads the setting and generates config.js; no Vite build is required for this separate page. The environment variable takes priority. Only the public backend base URL is exposed to the browser.

The API connection is in api.js; app.js renders its response. Search requests are:

```http
POST /api/faculty/search
Content-Type: application/json

{"query":"machine learning","top_k":10}
```

The adapter supports loading, cancel, timeout, HTTP/network errors and insufficient evidence. It never replaces an error with fabricated faculty. Raw scores are displayed without converting them into probability percentages. Missing expertise or verification fields are labeled honestly.

## Tests and provenance

From repository root:

```bash
python3 scripts/verify_upstream.py
node --test scripts/check_faculty_api_client.mjs
python3 scripts/test_live_faculty_api.py
python3 scripts/export_openalex_dataset.py
```

On Windows use py -3 in place of python3. The live test script requires the backend to be running and refreshes dataset snapshots. Run upstream tests from backend/ with `.venv/bin/python -m pytest` (Windows: `.\.venv\Scripts\python.exe -m pytest`).

## Original website

From repository root: `npm ci` then `npm run dev`. This starts the unchanged React demonstration separately. Its data remains synthetic. The separate HTML page is the live API integration; no change has been made to the published site's Faculty Assistant.

For remote hosting, deploy FastAPI to a Python host and set VITE_API_BASE_URL to its HTTPS address. localhost always refers to the machine running the browser. The imported server currently allows wildcard CORS; configure deployment access controls separately before a public rollout.
