import { useEffect, useState } from "react";

interface Institution {
  id: string | null;
  name: string;
}

interface Publication {
  work_id: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  citation_url: string | null;
}

interface Evidence {
  quote: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  source_url: string | null;
  expertise_type: string;
  relevance: number;
  work_id: string | null;
  doc_id: string | null;
}

interface Signal {
  name: string;
  value: number;
  weight: number;
  contribution: number;
  explanation: string;
}

interface FacultyMatch {
  faculty_id: string;
  faculty_name: string;
  score: number;
  expertise_type: string;
  stated_score: number;
  evidence_score: number;
  inferred_score: number;
  institutions: Institution[];
  stated_topics: string[];
  matched_topics: string[];
  supporting_publications: Publication[];
  evidence: Evidence[];
  signals: Signal[];
  notes: string[];
}

interface Citation {
  evidence_id: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  source_url: string | null;
  quote: string;
  work_id: string | null;
  faculty_id: string | null;
}

interface Claim {
  text: string;
  expertise_type: string;
  status: string;
  verification_note: string | null;
  citations: Citation[];
}

interface Health {
  status: string;
  mode?: string;
  corpus_source: string;
  profiles?: number;
  documents?: number;
  scope_institutions?: string[];
  llm_model: string | null;
}

interface SearchResponse {
  query: string;
  status: string;
  verified: boolean;
  answer_text: string;
  warnings: string[];
  llm_model: string | null;
  matches: FacultyMatch[];
  claims: Claim[];
}

const PRESET_QUERIES = [
  "graph neural networks",
  "protein folding dynamics",
  "xylophone concerto",
];

const TYPE_STYLES: Record<string, string> = {
  STATED: "bg-emerald-100 text-emerald-800 border-emerald-300",
  EVIDENCE_BASED: "bg-sky-100 text-sky-800 border-sky-300",
  INFERRED: "bg-amber-100 text-amber-800 border-amber-300",
};

function Badge({ label }: { label: string }) {
  const style = TYPE_STYLES[label] ?? "bg-gray-100 text-gray-800 border-gray-300";
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold ${style}`}>
      {label}
    </span>
  );
}

function DoiLink({ doi, sourceUrl }: { doi: string | null; sourceUrl: string | null }) {
  if (!doi && !sourceUrl) return <span className="text-gray-400">no link</span>;
  const href = sourceUrl ?? (doi ? `https://doi.org/${doi}` : null);
  if (!href) return <span className="text-gray-400">no link</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-sky-700 underline break-all"
    >
      {doi ? `doi:${doi}` : href}
    </a>
  );
}

function FacultyCard({ match }: { match: FacultyMatch }) {
  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xl font-bold text-gray-900">{match.faculty_name}</h2>
        <Badge label={match.expertise_type} />
      </div>
      <p className="mt-1 text-sm text-gray-600">
        {match.institutions.map((i) => i.name).join("; ") || "No institution recorded"}
        {"  "}· score {match.score.toFixed(3)}
      </p>
      <div className="mt-2 h-2 w-full overflow-hidden rounded bg-gray-100">
        <div className="h-full rounded bg-sky-600" style={{ width: `${match.score * 100}%` }} />
      </div>
      <p className="mt-2 text-xs text-gray-500">
        stated {match.stated_score.toFixed(3)} · evidence {match.evidence_score.toFixed(3)} · inferred{" "}
        {match.inferred_score.toFixed(3)}
      </p>

      {match.stated_topics.length > 0 && (
        <section className="mt-3">
          <h3 className="text-sm font-semibold text-gray-800">Stated expertise (declared)</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-gray-700">
            {match.stated_topics.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </section>
      )}

      {match.matched_topics.length > 0 && (
        <section className="mt-3">
          <h3 className="text-sm font-semibold text-gray-800">Matched topics</h3>
          <p className="mt-1 text-sm text-gray-700">{match.matched_topics.join(", ")}</p>
        </section>
      )}

      <section className="mt-3">
        <h3 className="text-sm font-semibold text-gray-800">
          Supporting publications ({match.supporting_publications.length})
        </h3>
        <ul className="mt-1 space-y-2">
          {match.supporting_publications.map((p) => (
            <li key={p.work_id} className="rounded border border-gray-100 bg-gray-50 p-2 text-sm">
              <span className="font-medium text-gray-900">{p.title ?? p.work_id}</span>
              <span className="text-gray-500"> ({p.year ?? "n.d."})</span>
              <div className="mt-1 text-xs">
                <DoiLink doi={p.doi} sourceUrl={p.citation_url} />
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-3">
        <h3 className="text-sm font-semibold text-gray-800">Evidence passages ({match.evidence.length})</h3>
        <ul className="mt-1 space-y-2">
          {match.evidence.map((e, i) => (
            <li key={i} className="rounded border border-gray-100 bg-gray-50 p-2 text-sm">
              <div className="mb-1 flex items-center gap-2">
                <Badge label={e.expertise_type} />
                <span className="text-xs text-gray-500">relevance {e.relevance.toFixed(2)}</span>
              </div>
              <blockquote className="border-l-2 border-sky-300 pl-2 text-gray-700">“{e.quote}”</blockquote>
              <div className="mt-1 text-xs text-gray-500">
                {e.title} ({e.year ?? "n.d."}) · <DoiLink doi={e.doi} sourceUrl={e.source_url} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export default function App() {
  const [query, setQuery] = useState("graph neural networks");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setHealth(data as Health))
      .catch(() => {});
  }, []);

  async function search(q: string) {
    const trimmed = q.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/faculty/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, top_k: 10 }),
      });
      if (!res.ok) throw new Error(`backend responded ${res.status}`);
      setResult((await res.json()) as SearchResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const insufficient = result !== null && result.status === "insufficient_evidence";

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <header>
          <h1 className="text-3xl font-bold">Faculty Research Discovery</h1>
          <p className="mt-1 text-sm text-gray-600">
            Live demo: every result is computed by the real RAG pipeline (BM25 + vectors + hybrid +
            rerank + expertise + evidence + verification). Nothing is hardcoded.
          </p>
          <p className="mt-1 text-xs text-gray-500">
            {health
              ? `Searching ${health.scope_institutions?.length ? `institutions ${health.scope_institutions.join(", ")}` : "the global OpenAlex universe"}${health.profiles !== undefined ? ` · ${health.profiles} profiles · ${health.documents} chunks` : ""} · corpus: ${health.corpus_source} · ${health.llm_model}`
              : "Connecting to backend…"}
          </p>
        </header>

        <div className="mt-4 flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search(query)}
            placeholder="e.g. graph neural networks"
            className="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2"
          />
          <button
            onClick={() => search(query)}
            disabled={loading}
            className="rounded-lg bg-sky-700 px-4 py-2 font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-2 flex flex-wrap gap-2">
          {PRESET_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => {
                setQuery(q);
                search(q);
              }}
              className="rounded-full border border-sky-300 bg-sky-50 px-3 py-1 text-sm text-sky-800"
            >
              {q}
            </button>
          ))}
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">
            Request failed: {error}. Is the backend running on :8000?
          </div>
        )}

        {result && insufficient && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
            <p className="font-semibold text-amber-900">insufficient_evidence</p>
            <p className="mt-1 text-sm text-amber-800">{result.answer_text}</p>
            <p className="mt-1 text-xs text-amber-700">
              Zero results shown — the system refuses to fabricate faculty, scores, or citations.
            </p>
          </div>
        )}

        {result && !insufficient && (
          <>
            <div
              className={`mt-4 rounded-lg border p-3 text-sm ${
                result.verified
                  ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                  : "border-red-300 bg-red-50 text-red-900"
              }`}
            >
              <span className="font-semibold">
                {result.verified ? "✓ verified" : "✗ NOT verified"}
              </span>{" "}
              · {result.claims.length} claim(s) · model {result.llm_model ?? "unknown"}
              {result.warnings.map((w) => (
                <span key={w} className="ml-2 text-xs">
                  ⚠ {w}
                </span>
              ))}
            </div>

            <div className="mt-4 space-y-4">
              {result.matches.map((m) => (
                <FacultyCard key={m.faculty_id} match={m} />
              ))}
            </div>

            <section className="mt-6">
              <h2 className="text-lg font-bold">Verified claims & citations</h2>
              <div className="mt-2 space-y-3">
                {result.claims.map((c, i) => (
                  <div key={i} className="rounded-xl border border-gray-200 bg-white p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge label={c.expertise_type} />
                      <span
                        className={`text-xs font-semibold ${
                          c.status === "supported" ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-gray-800">{c.text}</p>
                    {c.verification_note && (
                      <p className="mt-1 text-xs text-gray-500">{c.verification_note}</p>
                    )}
                    <ul className="mt-2 space-y-1 text-xs text-gray-600">
                      {c.citations.map((cit) => (
                        <li key={cit.evidence_id} className="rounded bg-gray-50 p-2">
                          <span className="font-medium text-gray-800">
                            {cit.title} ({cit.year ?? "n.d."})
                          </span>
                          <div className="mt-1">
                            <DoiLink doi={cit.doi} sourceUrl={cit.source_url} />
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
