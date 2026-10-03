'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';
import { ExportButtons, NotesPanel, CitationModal } from './Widgets';

// Faculty Discovery (Research AI system): shows the SESSION's real backend
// RAG matches. The classic demo corpus stays at /discover, untouched.
export function FacultyPage({ sessionId }: { sessionId?: string | null }) {
  const ctx = useSession();
  const sid = sessionId || ctx.sessionId;
  const [data, setData] = useState<any | null>(null);
  useEffect(() => {
    let live = true;
    if (sid) api.session(sid).then((s: any) => live && setData(s)).catch(() => {});
    return () => { live = false; };
  }, [sid, ctx.session]);
  const matches = data?.results?.faculty?.matches || [];
  const verified = data?.results?.faculty?.verified;
  return (
    <div className="workspace">
      <span className="eyebrow blue">FACULTY DISCOVERY · PS23 CORE</span>
      <h1>Faculty Discovery</h1>
      {data ? <p className="session-idea">Active research: <strong>{data.idea}</strong></p> : <p className="muted">Open a research session from the Dashboard to see evidence-backed matches here.</p>}
      {data && verified !== undefined && (
        <p className={`verify-badge ${verified ? 'ok' : 'warn'}`}>{verified ? '✓ Verified against corpus' : '! Unverified — treat cautiously'}</p>
      )}
      {matches.length ? matches.map((f: any) => (
        <article key={f.faculty_id} className="faculty-card">
          <h3>{f.faculty_name}</h3>
          <p className="small muted">Research match: {Math.round((f.score || 0) * 100)}% · {f.expertise_type}</p>
          <div className="tags">{(f.matched_topics || []).map((t: string) => <span className="tag" key={t}>{t}</span>)}</div>
          <div className="evidence-card"><div className="eyebrow">Publication evidence</div>
            {(f.evidence || []).map((e: any, i: number) => <p key={i}>“{e.title}” ({e.year || 'n.d.'}){e.doi ? ` · doi:${e.doi}` : ''}</p>)}
          </div>
        </article>
      )) : data ? <p className="muted">No faculty evidence in this session yet.</p> : null}
      <p><Link className="text-button" href={sid ? `/discover?session=${sid}` : '/discover'}>Open classic Faculty Assistant (demo corpus)</Link></p>
    </div>
  );
}

// Research Analysis: renders stored comparison + derived findings. No new API.
export function AnalysisPage({ sessionId }: { sessionId?: string | null }) {
  const ctx = useSession();
  const sid = sessionId || ctx.sessionId;
  const [data, setData] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    let live = true;
    if (sid) api.session(sid).then((s: any) => live && setData(s)).catch(() => {});
    return () => { live = false; };
  }, [sid, ctx.session]);
  const analysis = data?.results?.analysis;
  const papers = data?.results?.literature?.papers || [];
  const { events, runStages } = ctx;
  if (!data) return <div className="workspace"><span className="eyebrow blue">RESEARCH ANALYSIS</span><h1>Research Analysis</h1><p className="muted">Open a research session from the Dashboard.</p></div>;
  const years = papers.map((p: any) => p.year).filter(Boolean).sort();
  const byYear: Record<string, number> = {};
  papers.forEach((p: any) => { if (p.year) byYear[p.year] = (byYear[p.year] || 0) + 1; });
  return (
    <div className="workspace">
      <span className="eyebrow blue">RESEARCH ANALYSIS</span>
      <h1>Research Analysis</h1>
      <p className="session-idea">Active research: <strong>{data.idea}</strong></p>
      {!analysis && (
        <div className="card-bottom" style={{ marginBottom: 12 }}>
          <button className="button primary" disabled={running || ctx.running} onClick={() => { setRunning(true); runStages(['analysis']).finally(() => setRunning(false)); }}>
            Run analysis
          </button>
        </div>
      )}
      {analysis ? (
        <>
          <div className="two-col">
            <article className="research-card"><h3>Key Findings</h3>
              <p className="small muted">{papers.length} papers · {years.length ? `${years[0]}–${years[years.length - 1]}` : 'years unknown'} · open access {analysis.open_access_share}</p>
              <p className="small muted">Top topics: {Object.keys(analysis.top_topics || {}).slice(0, 5).join(', ') || '—'}</p>
            </article>
            <article className="research-card"><h3>Research Trends</h3>
              {Object.keys(byYear).length ? Object.entries(byYear).sort().map(([y, n]) => <p key={y} className="small muted rail-item">{y} — {n} papers</p>) : <p className="small muted">No year data.</p>}
            </article>
          </div>
          <article className="research-card"><h3>Methodologies & Topics</h3>
            <div className="tags">{Object.keys(analysis.top_topics || {}).map((t) => <span className="tag" key={t}>{t}</span>)}</div>
          </article>
          <article className="research-card"><h3>Datasets</h3>
            <p className="small muted">Dataset-level metadata is not available in OpenAlex records — dataset gaps are inferred from topic sparsity on the Gaps page, not fabricated here.</p>
          </article>
          <article className="research-card"><h3>Limitations</h3>
            <p className="small muted">Limitations cannot be inferred from metadata alone; consult full texts of the important papers below.</p>
          </article>
          <article className="research-card"><h3>Important Papers (most cited)</h3>
            {(analysis.most_cited || []).map((t: string, i: number) => <p key={i} className="small muted rail-item">· {t}</p>)}
          </article>
          <article className="research-card"><h3>Comparison Matrix</h3>
            <div className="comparison-scroll"><table className="compare-table"><thead><tr><th>Title</th><th>Year</th><th>Topics</th><th>Cited</th></tr></thead>
              <tbody>{(analysis.comparison || []).map((r: any, i: number) => (
                <tr key={i}><td>{r.title}</td><td>{r.year || '—'}</td><td>{(r.topics || []).join(', ')}</td><td>{r.cited_by_count}</td></tr>
              ))}</tbody></table></div>
          </article>
          <article className="research-card"><h3>Literature Review</h3>
            <p><strong>Summary.</strong> <span className="small muted">{papers.length} retrieved works{years.length ? ` spanning ${years[0]}–${years[years.length - 1]}` : ''}; open access {analysis.open_access_share}.</span></p>
            <p><strong>Major themes.</strong> <span className="small muted">{Object.keys(analysis.top_topics || {}).slice(0, 6).join('; ') || '—'}</span></p>
            <p><strong>Research trends.</strong> <span className="small muted">{Object.keys(byYear).length ? `Publication activity by year recorded above; latest year ${years[years.length - 1]}.` : 'Insufficient year data.'}</span></p>
            <p><strong>Existing approaches.</strong> <span className="small muted">Approaches cluster around the listed themes; method-level detail requires full texts.</span></p>
            <p><strong>Research gaps.</strong> <span className="small muted">{((data?.results?.gaps?.gaps) || []).length ? (data.results.gaps.gaps as any[]).map((g: any) => g.title).join('; ') : 'Run Gaps & Novelty to populate.'}</span></p>
            <p><strong>References.</strong></p>
            {(analysis.most_cited || []).map((t: string, i: number) => <p key={i} className="small muted rail-item">[{i + 1}] {t}</p>)}
          </article>
          <div className="two-col">
            <article className="research-card"><h3>Research Notes</h3><NotesPanel sessionId={sid} /></article>
            <article className="research-card"><h3>Export</h3><ExportButtons session={data} /></article>
          </div>
        </>
      ) : <p className="muted">No analysis in this session yet — run it to compare the retrieved papers.</p>}
    </div>
  );
}

// Projects = sessions with real progress. Saved/Drafts/History derive from them.
export function ProjectsPage() {
  const [sessions, setSessions] = useState<any[]>([]);
  useEffect(() => { api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {}); }, []);
  const order = ['idea', 'faculty', 'literature', 'analysis', 'gaps', 'direction', 'planner', 'paper'];
  return (
    <div className="workspace">
      <span className="eyebrow blue">MY RESEARCH</span><h1>Projects</h1>
      {sessions.length ? sessions.map((s) => {
        const done = Object.values(s.stage_status || {}).filter((v) => v === 'done').length;
        const current = order.find((k) => (s.stage_status || {})[k] !== 'done') || 'paper';
        return (
          <article key={s.id} className="research-card">
            <h3>{s.idea}</h3>
            <div className="progress-track"><div className="progress-fill" style={{ width: `${Math.round((done / 8) * 100)}%` }} /></div>
            <p className="small muted">{Math.round((done / 8) * 100)}% · stage: {current} · {(s.results?.literature?.papers || []).length} papers · {(s.results?.faculty?.matches || []).length} faculty · {(s.results?.gaps?.gaps || []).length} gaps</p>
            <Link className="button secondary small-btn" href={`/app?session=${s.id}`}>Open</Link>
          </article>
        );
      }) : <div className="research-card empty-card"><h3>No research activity yet</h3><p className="muted">Create a session from the Dashboard.</p></div>}
    </div>
  );
}

export function SavedPage() {
  const { sessionId } = useSession();
  const [sessions, setSessions] = useState<any[]>([]);
  const [cited, setCited] = useState<any | null>(null);
  const load = () => api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {});
  useEffect(() => { load(); }, []);
  const all = sessions.flatMap((s) => ((s.results?.saved_papers?.papers) || []).map((p: any) => ({ ...p, _sid: s.id })));
  return (
    <div className="workspace">
      <span className="eyebrow blue">MY RESEARCH</span><h1>Saved Papers</h1>
      {all.length ? all.map((p: any) => (
        <article key={`${p._sid}:${p.id}`} className="publication-item">
          <div><div className="eyebrow">{p.year || 'n.d.'}</div><h3>{p.title || p.id}</h3>
            <div className="card-bottom">
              <span className="subtle-link">{p.doi ? `doi:${p.doi}` : ''}</span>
              <button className="subtle-link" onClick={() => setCited(p)}>Cite</button>
              {p._sid === sessionId && <button className="subtle-link" onClick={async () => { await api.removePaper(p._sid, p.id); load(); }}>Remove</button>}
            </div>
          </div>
        </article>
      )) : <div className="research-card empty-card"><h3>No saved papers</h3><p className="muted">Save papers from Literature Search.</p></div>}
      {cited && <CitationModal paper={cited} sessionId={sessionId} onClose={() => setCited(null)} />}
    </div>
  );
}

export function DraftsPage() {
  const [sessions, setSessions] = useState<any[]>([]);
  useEffect(() => { api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {}); }, []);
  const drafts = sessions.filter((s) => s.results?.paper?.draft || s.results?.planner?.plan_text);
  return (
    <div className="workspace">
      <span className="eyebrow blue">MY RESEARCH</span><h1>Drafts</h1>
      {drafts.length ? drafts.map((s) => (
        <article key={s.id} className="research-card"><h3>{s.idea?.slice(0, 80)}</h3>
          <p className="small muted">{s.results?.paper?.draft ? 'Paper outline' : ''}{s.results?.paper?.draft && s.results?.planner?.plan_text ? ' · ' : ''}{s.results?.planner?.plan_text ? 'Research plan' : ''}</p>
          <Link className="button secondary small-btn" href={`/paper-studio?session=${s.id}`}>Open in Studio</Link>
        </article>
      )) : <div className="research-card empty-card"><h3>No drafts</h3><p className="muted">Drafts appear after running Planner or Paper stages.</p></div>}
    </div>
  );
}

export function HistoryPage() {
  const [sessions, setSessions] = useState<any[]>([]);
  useEffect(() => { api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {}); }, []);
  const items = sessions.flatMap((s) => (s.activity || []).map((a: any) => ({ ...a, idea: s.idea }))).reverse().slice(0, 60);
  return (
    <div className="workspace">
      <span className="eyebrow blue">MY RESEARCH</span><h1>Research History</h1>
      {items.length ? items.map((a: any, i: number) => (
        <p key={i} className="small muted rail-item"><strong>{a.stage}</strong> · {a.message} <span className="muted">— {String(a.idea).slice(0, 60)}</span></p>
      )) : <div className="research-card empty-card"><h3>No research activity yet</h3><p className="muted">Activity is recorded as stages run.</p></div>}
    </div>
  );
}

export function SettingsPage() {  const [providers, setProviders] = useState<any[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { api.providers().then((d: any) => setProviders(d.providers || [])).catch((e: any) => setError(String(e.message || e))); }, []);
  return (
    <div className="workspace">
      <span className="eyebrow blue">SYSTEM</span><h1>Settings</h1>
      <article className="research-card"><h3>AI Providers</h3>
        {error ? <p className="muted">Backend unreachable: {error.slice(0, 150)}</p> :
          providers.map((p) => (
            <p key={p.name} className="small muted rail-item">{p.name} · {p.model} · {p.available ? 'available' : 'not configured'}{p.configured ? ' · active' : ''}</p>
          ))}
        <p className="small muted">API keys live on the backend only and are never shown here. Ollama is reserved for later.</p>
      </article>
      <article className="research-card"><h3>Backend</h3><p className="small muted">{api.base} · Faculty RAG + OpenAlex retrieval stays the discovery core.</p></article>
    </div>
  );
}

// Paper Explainer: real record metadata only. Full-text method/result
// breakdowns are NOT invented — abstract excerpts are labeled as excerpts.
export function PaperPage({ paperId, sessionId }: { paperId: string | null; sessionId?: string | null }) {
  const [paper, setPaper] = useState<any | null>(null);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!paperId) return;
    api.base; // base URL only; no secrets here
    fetch(`${api.base}/api/papers/${encodeURIComponent(paperId)}`)
      .then((r) => { if (!r.ok) throw new Error(`Backend ${r.status}`); return r.json(); })
      .then(setPaper)
      .catch((e: any) => setError(String(e.message || e)));
  }, [paperId]);
  if (!paperId) return <div className="workspace"><h1>Paper Explainer</h1><p className="muted">Open a paper from Literature Search.</p></div>;
  if (error) return <div className="workspace"><h1>Paper Explainer</h1><p className="muted">Paper unavailable: {error.slice(0, 200)}</p></div>;
  if (!paper) return <div className="workspace"><h1>Paper Explainer</h1><p className="muted">Loading record…</p></div>;
  const excerpt = (paper.abstract || '').split(/(?<=[.!?])\s+/).slice(0, 2).join(' ');
  const section = (title: string, body: React.ReactNode) => (
    <article className="research-card"><h3>{title}</h3>{body}</article>
  );
  return (
    <div className="workspace">
      <span className="eyebrow blue">PAPER EXPLAINER</span>
      <h1>{paper.title || paper.id}</h1>
      <p className="small muted">
        {(paper.authors || []).slice(0, 6).map((a: any) => a.name).join(', ') || 'Authors not in record'}
        {' · '}{paper.year || 'n.d.'}{paper.venue ? ` · ${paper.venue}` : ''}
        {typeof paper.cited_by_count === 'number' && ` · Cited by ${paper.cited_by_count}`}
      </p>
      {section('TL;DR', <><p>{excerpt || 'No abstract in record.'}</p><p className="small muted">Opening excerpt of the recorded abstract — verify in the full text.</p></>)}
      {section('Research problem', <><p>{excerpt || 'Not stated in record.'}</p><p className="small muted">Framed from the abstract excerpt only.</p></>)}
      {section('Methodology & Results', <p className="small muted">Full-text analysis unavailable — the record carries metadata and abstract only. Open the source below for methods and results.</p>)}
      {section('Topics & Concepts', <div className="tags">{[...(paper.topics || []), ...(paper.keywords || []).slice(0, 5)].map((t: string) => <span className="tag" key={t}>{t}</span>)}</div>)}
      {section('Limitations & Gaps', <p className="small muted">Limitations need the full text. Session-level gaps live on the Gaps page.</p>)}
      <div className="card-bottom">
        {paper.doi && <a className="button secondary small-btn" href={`https://doi.org/${paper.doi}`}>Open source</a>}
        {sessionId && !saved && (
          <button className="button secondary small-btn" onClick={async () => {
            await api.savePaper(sessionId, { id: paper.id, title: paper.title, year: paper.year, doi: paper.doi, abstract: paper.abstract, topics: paper.topics, cited_by_count: paper.cited_by_count });
            setSaved(true);
          }}>Save source</button>
        )}
        {saved && <span className="small muted">Saved ✓</span>}
      </div>
    </div>
  );
}

// Collections: user-named groups of sessions, stored locally (real user data).
type Collection = { id: string; name: string; sessionIds: string[] };
function loadCollections(): Collection[] {
  try { return JSON.parse(localStorage.getItem('research-collections') || '[]'); } catch { return []; }
}
export function CollectionsPage() {
  const [cols, setCols] = useState<Collection[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [name, setName] = useState('');
  useEffect(() => {
    setCols(loadCollections());
    api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {});
  }, []);
  const persist = (next: Collection[]) => {
    setCols(next);
    try { localStorage.setItem('research-collections', JSON.stringify(next)); } catch {}
  };
  const byId = new Map(sessions.map((s) => [s.id, s]));
  return (
    <div className="workspace">
      <span className="eyebrow blue">MY RESEARCH</span><h1>Collections</h1>
      <div className="note-add">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New collection name…" aria-label="New collection" maxLength={80} />
        <button className="button secondary small-btn" onClick={() => {
          if (!name.trim()) return;
          persist([{ id: Math.random().toString(36).slice(2, 10), name: name.trim(), sessionIds: [] }, ...cols]);
          setName('');
        }}>Create</button>
      </div>
      {cols.length ? cols.map((c) => (
        <article key={c.id} className="research-card">
          <h3>{c.name}</h3>
          {(c.sessionIds || []).map((sid) => byId.get(sid)).filter(Boolean).map((s: any) => (
            <p key={s.id} className="small muted rail-item"><Link href={`/app?session=${s.id}`}>{s.idea?.slice(0, 80)}</Link>
              {' '}<button className="subtle-link" onClick={() => persist(cols.map((x) => x.id === c.id ? { ...x, sessionIds: x.sessionIds.filter((i) => i !== s.id) } : x))}>Remove</button></p>
          ))}
          {!c.sessionIds?.length && <p className="small muted">Empty — add sessions below.</p>}
          <div className="card-bottom">
            <select aria-label={`Add session to ${c.name}`} defaultValue="" onChange={(e) => {
              if (!e.target.value) return;
              persist(cols.map((x) => x.id === c.id && !x.sessionIds.includes(e.target.value) ? { ...x, sessionIds: [...x.sessionIds, e.target.value] } : x));
            }}>
              <option value="">Add research…</option>
              {sessions.filter((s) => !c.sessionIds.includes(s.id)).map((s) => <option key={s.id} value={s.id}>{(s.idea || '').slice(0, 60)}</option>)}
            </select>
            <button className="subtle-link" onClick={() => persist(cols.filter((x) => x.id !== c.id))}>Delete collection</button>
          </div>
        </article>
      )) : <div className="research-card empty-card"><h3>No collections</h3><p className="muted">Group related research threads together.</p></div>}
    </div>
  );
}

// Analytics: ONLY real stored data. Empty states where nothing exists.
export function AnalyticsPage() {
  const [sessions, setSessions] = useState<any[]>([]);
  useEffect(() => { api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => {}); }, []);
  if (!sessions.length) {
    return <div className="workspace"><span className="eyebrow blue">ANALYTICS</span><h1>Analytics</h1>
      <div className="research-card empty-card"><h3>No research activity yet</h3><p className="muted">Statistics appear once research sessions exist.</p></div></div>;
  }
  const papers = sessions.reduce((n, s) => n + (s.results?.literature?.papers || []).length, 0);
  const faculty = sessions.reduce((n, s) => n + (s.results?.faculty?.matches || []).length, 0);
  const gaps = sessions.reduce((n, s) => n + (s.results?.gaps?.gaps || []).length, 0);
  const saved = sessions.reduce((n, s) => n + (s.results?.saved_papers?.papers || []).length, 0);
  const activity = sessions.reduce((n, s) => n + (s.activity || []).length, 0);
  const topicCounts = new Map<string, number>();
  sessions.forEach((s) => (s.results?.literature?.papers || []).forEach((p: any) =>
    (p.topics || []).forEach((t: string) => topicCounts.set(t, (topicCounts.get(t) || 0) + 1))));
  const cards: Array<[string, string]> = [
    ['Research queries', String(sessions.length)], ['Documents (papers)', String(papers)],
    ['Faculty discovered', String(faculty)], ['Gaps identified', String(gaps)],
    ['Saved sources', String(saved)], ['Research activity events', String(activity)],
  ];
  return (
    <div className="workspace">
      <span className="eyebrow blue">ANALYTICS</span><h1>Analytics</h1>
      <p className="muted">Computed from stored sessions — no sampled or demo numbers.</p>
      <div className="three-features">
        {cards.map(([label, value]) => (
          <article key={label}><span className="eyebrow blue">{label.toUpperCase()}</span><h3>{value}</h3></article>
        ))}
      </div>
      <article className="research-card" style={{ marginTop: 14 }}><h3>Top topics across research</h3>
        {[...topicCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([t, n]) => (
          <p key={t} className="small muted rail-item">{t} <strong>×{n}</strong></p>
        ))}
      </article>
    </div>
  );
}

// Documents: backend corpus/index status (REAL). Personal upload is NOT
// supported by the backend, so the UI says so instead of faking it.
export function DocumentsPage() {
  const [health, setHealth] = useState<any | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    fetch(`${api.base}/health`).then((r) => { if (!r.ok) throw new Error(`Backend ${r.status}`); return r.json(); })
      .then(setHealth).catch((e: any) => setError(String(e.message || e)));
  }, []);
  return (
    <div className="workspace">
      <span className="eyebrow blue">SOURCES</span><h1>Documents</h1>
      {error && <p className="muted">Backend unreachable: {error.slice(0, 150)}</p>}
      {health && (
        <article className="research-card"><h3>Research index status</h3>
          <p className="small muted rail-item">Mode: {health.mode} · Source: {health.corpus_source}</p>
          {typeof health.profiles === 'number' && <p className="small muted rail-item">Indexed profiles: {health.profiles}</p>}
          {typeof health.documents === 'number' && <p className="small muted rail-item">Indexed documents: {health.documents}</p>}
          {health.scope_institutions && <p className="small muted rail-item">Scope: {(health.scope_institutions as string[]).join(', ') || 'global OpenAlex'}</p>}
        </article>
      )}
      <article className="research-card"><h3>Uploads</h3>
        <p className="small muted">Personal document upload is not supported by the backend yet — the index is built from OpenAlex retrieval, not uploads. Your saved papers live under Saved Sources.</p>
        <Link className="button secondary small-btn" href="/saved">Open Saved Sources</Link>
      </article>
    </div>
  );
}
