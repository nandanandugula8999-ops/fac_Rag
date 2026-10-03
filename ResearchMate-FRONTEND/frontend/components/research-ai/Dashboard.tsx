'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Search, ScanSearch, BookOpen, ChartNoAxesCombined, Lightbulb, FlaskConical, FileText, ArrowRight } from 'lucide-react';
import RunProgress from './RunProgress';
import { useSession, withSession } from '@/lib/session';
import { api } from '@/lib/api';

// Dashboard = central workspace. Idea typed ONCE; Analyze creates/updates the
// session and runs a literature baseline live — user stays on this page.
const QUICK = [
  { label: 'Faculty Discovery', href: '/faculty', Icon: ScanSearch, note: 'Find researchers and explore expertise' },
  { label: 'Literature Search', href: '/literature', Icon: BookOpen, note: 'Search and analyze research papers' },
  { label: 'Research Analysis', href: '/analysis', Icon: ChartNoAxesCombined, note: 'Compare papers and identify trends' },
  { label: 'Gaps & Novelty', href: '/gaps', Icon: Lightbulb, note: 'Discover research gaps and opportunities' },
  { label: 'Research Planner', href: '/planner', Icon: FlaskConical, note: 'Create a structured research plan' },
  { label: 'Paper Studio', href: '/paper-studio', Icon: FileText, note: 'Write, refine and export your paper' },
];
const ACTIONS = [
  { label: 'Literature Search', href: '/literature', Icon: BookOpen },
  { label: 'Find Faculty', href: '/faculty', Icon: ScanSearch },
  { label: 'Analyze Gaps', href: '/gaps', Icon: Lightbulb },
  { label: 'Plan Research', href: '/planner', Icon: FlaskConical },
  { label: 'Write Paper', href: '/paper-studio', Icon: FileText },
];

function greeting(d: Date | null) {
  if (!d) return 'Good evening';
  const h = d.getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

export default function Dashboard({ user }: { user: string }) {
  const { session, sessionId, events, running, createSession, selectSession, runStages, refresh } = useSession();
  const [idea, setIdea] = useState('');
  const [provider, setProvider] = useState('checking…');
  const [model, setModel] = useState('');
  const [sessions, setSessions] = useState<any[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [backendDown, setBackendDown] = useState(false);
  // Client-only clock: SSR renders empty so hydration never mismatches.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => { setNow(new Date()); }, []);
  // Fresh input per session: switching sessions must not show stale text.
  useEffect(() => { setIdea(''); }, [sessionId]);

  useEffect(() => {
    try { setRecent(JSON.parse(localStorage.getItem('faculty-recent') || '[]')); } catch {}
    api.providers()
      .then((d: any) => {
        const g = (d.providers || []).find((p: any) => p.name === 'groq');
        const o = (d.providers || []).find((p: any) => p.name === 'ollama');
        if (g?.available) { setProvider('Groq'); setModel(g.model); }
        else { setProvider('Offline evidence mode'); setModel(o?.available ? o.model : 'extractive-v1'); }
      })
      .catch(() => { setBackendDown(true); setProvider('Backend unreachable'); });
    api.sessions().then((d: any) => setSessions(d.sessions || [])).catch(() => setBackendDown(true));
  }, [session]);

  // ?session= deep link selects without navigating away.
  useEffect(() => {
    try {
      const sid = new URLSearchParams(window.location.search).get('session');
      if (sid && sid !== sessionId) selectSession(sid);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function analyze() {
    const text = (session ? idea || session.idea : idea).trim();
    if (!text || running) return;
    setError('');
    try {
      if (session && text !== session.idea) {
        await api.updateSession(session.id, { idea: text });
        await refresh();
      } else if (!session) {
        await createSession(text);
      }
      try {
        const r = [text, ...recent.filter((x) => x !== text)].filter(Boolean).slice(0, 5);
        setRecent(r);
        localStorage.setItem('faculty-recent', JSON.stringify(r));
      } catch {}
      // Baseline only: literature search with live progress. User stays here.
      runStages(['literature']);
    } catch (e: any) {
      setError(String(e.message || e));
    }
  }

  const papers = session?.results?.literature?.papers || [];
  const faculty = session?.results?.faculty?.matches || [];
  const topics = useMemo(() => {
    const counts = new Map<string, number>();
    papers.forEach((p: any) => (p.topics || []).forEach((t: string) => counts.set(t, (counts.get(t) || 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [papers]);
  const dateStr = now ? now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }) : '';

  return (
    <div className="dash-grid">
      <div className="workspace research-dash">
        <p className="small muted">{dateStr}{session ? ` · Session ${sessionId}` : ' · No active session'}</p>
        <h1>{greeting(now)}{user ? `, ${user}` : ''} 👋</h1>
        <p>Your AI-powered research workspace</p>

        <section className="research-card hero-card">
          <h2>What are you researching today?</h2>
          <p className="muted">Ask a question, describe your research idea, or choose a task.</p>
          <form onSubmit={(e) => { e.preventDefault(); analyze(); }}>
            <textarea aria-label="Research idea" value={session && !idea ? session.idea : idea} onChange={(e) => setIdea(e.target.value)}
              placeholder="e.g. Lightweight CNNs for diabetic retinopathy, research gaps in medical imaging..."
              rows={3} maxLength={2000} disabled={running} />
            <div className="hero-row">
              <span className="provider-line">AI Provider: <strong>{provider}</strong>{model ? ` · Model: ${model}` : ''}</span>
              <button className="button primary" type="submit" disabled={running}>
                {running ? 'Analyzing…' : 'Analyze Research →'}
              </button>
            </div>
          </form>
          {error && <p className="muted">Could not start research: {error.slice(0, 200)}</p>}
          {backendDown && <p className="muted">Backend unreachable — Faculty Discovery demo below still works offline.</p>}
          <div className="quick-actions">
            {ACTIONS.map(({ label, href, Icon }) => (
              <Link key={label} href={withSession(href, sessionId)} className="qa"><Icon size={15} />{label}</Link>
            ))}
          </div>
        </section>

        <RunProgress events={events} running={running} />

        <h2 style={{ marginTop: 22 }}>Continue Research</h2>
        {sessions.length ? (
          <div className="continue-grid">
            {sessions.slice(0, 4).map((s) => <ContinueCard key={s.id} s={s} active={s.id === sessionId} />)}
          </div>
        ) : (
          <div className="research-card empty-card"><h3>No research activity yet</h3><p className="muted">Enter an idea above to create your first research session.</p></div>
        )}

        <h2 style={{ marginTop: 22 }}>Quick Access</h2>
        <div className="topic-grid">
          {QUICK.map(({ label, href, Icon, note }) => (
            <Link key={label} href={withSession(href, sessionId)} className="topic-card">
              <span className="topic-icon tint-0"><Icon size={25} /></span><h3>{label}</h3><p>{note}</p><span className="topic-link">Open <ArrowRight size={13} /></span>
            </Link>
          ))}
        </div>

        <h2 style={{ marginTop: 22 }}>Recent Faculty Discoveries</h2>
        {session?.results?.faculty?.verified !== undefined && (
          <p className={`verify-badge ${session.results.faculty.verified ? 'ok' : 'warn'}`}>
            {session.results.faculty.verified ? '✓ Verified against corpus' : '! Unverified — treat cautiously'}
          </p>
        )}
        {faculty.length ? (
          <div className="continue-grid">
            {faculty.slice(0, 3).map((f: any) => (
              <article key={f.faculty_id} className="research-card">
                <h3>{f.faculty_name}</h3>
                <p className="small muted">Research match: {Math.round((f.score || 0) * 100)}% · {f.expertise_type}</p>
                <div className="tags">{(f.matched_topics || []).slice(0, 4).map((t: string) => <span className="tag" key={t}>{t}</span>)}</div>
                <p className="small muted">{(f.evidence || []).length} supporting publications</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="research-card empty-card"><h3>No faculty discovered yet</h3><p className="muted">Open Faculty Discovery to find researchers with evidence.</p></div>
        )}
      </div>

      <aside className="dash-rail">
        <section className="research-card">
          <h3>Recent Searches</h3>
          {recent.length ? recent.map((t) => <Link key={t} className="rail-link" href={`/discover?q=${encodeURIComponent(t)}`}>{t}</Link>)
            : <p className="small muted">No recent searches.</p>}
        </section>
        <section className="research-card">
          <h3>Research Activity</h3>
          {(session?.activity || []).length ? (session.activity as any[]).slice(-6).reverse().map((a: any, i: number) => (
            <p key={i} className="small muted rail-item">· {a.message}</p>
          )) : <p className="small muted">No research activity yet</p>}
        </section>
        <section className="research-card">
          <h3>Top Research Topics</h3>
          {topics.length ? topics.map(([t, n]) => (
            <p key={t} className="small muted rail-item">{t} <strong>×{n}</strong></p>
          )) : <p className="small muted">No topic statistics yet</p>}
        </section>
        <section className="research-card">
          <h3>Research Network</h3>
          {faculty.length ? faculty.slice(0, 5).map((f: any) => (
            <p key={f.faculty_id} className="small muted rail-item">{f.faculty_name} ↔ {(f.matched_topics || []).slice(0, 2).join(', ')}</p>
          )) : <p className="small muted">No network data yet</p>}
        </section>
      </aside>
    </div>
  );
}

function ContinueCard({ s, active }: { s: any; active: boolean }) {
  const { selectSession } = useSession();
  const done = Object.values(s.stage_status || {}).filter((v) => v === 'done').length;
  const pct = Math.round((done / 8) * 100);
  const order = ['idea', 'faculty', 'literature', 'analysis', 'gaps', 'direction', 'planner', 'paper'];
  const current = order.find((k) => (s.stage_status || {})[k] !== 'done') || 'paper';
  const papers = (s.results?.literature?.papers || []).length;
  const fac = (s.results?.faculty?.matches || []).length;
  const gaps = (s.results?.gaps?.gaps || []).length;
  const last = (s.activity || []).length ? s.activity[s.activity.length - 1].message : 'Created';
  return (
    <article className={`research-card ${active ? 'active-card' : ''}`}>
      <h3>{s.idea?.slice(0, 70)}</h3>
      <div className="progress-track"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
      <p className="small muted">{pct}% · {papers} papers · {fac} faculty · {gaps} gaps</p>
      <p className="small muted">Stage: {current} · {String(last).slice(0, 80)}</p>
      {active ? (
        <span className="small muted">Active session</span>
      ) : (
        <button className="button secondary small-btn" onClick={() => selectSession(s.id)}>Continue</button>
      )}
    </article>
  );
}
