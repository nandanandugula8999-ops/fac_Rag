'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useSession } from '@/lib/session';

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
  return (
    <div className="workspace">
      <span className="eyebrow blue">FACULTY DISCOVERY · PS23 CORE</span>
      <h1>Faculty Discovery</h1>
      {data ? <p className="session-idea">Active research: <strong>{data.idea}</strong></p> : <p className="muted">Open a research session from the Dashboard to see evidence-backed matches here.</p>}
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
              {p._sid === sessionId && <button className="subtle-link" onClick={async () => { await api.removePaper(p._sid, p.id); load(); }}>Remove</button>}
            </div>
          </div>
        </article>
      )) : <div className="research-card empty-card"><h3>No saved papers</h3><p className="muted">Save papers from Literature Search.</p></div>}
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

export function SettingsPage() {
  const [providers, setProviders] = useState<any[]>([]);
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
