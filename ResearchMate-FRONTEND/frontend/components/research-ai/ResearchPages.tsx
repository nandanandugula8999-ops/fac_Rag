'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Search } from 'lucide-react';
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { api, type Paper } from '@/lib/api';
import { useSession } from '@/lib/session';
import RunProgress from './RunProgress';
import { CitationModal, ExportButtons, NotesPanel } from './Widgets';

// All pages share one rule: with a session, the idea is NEVER retyped.
// Stored stage results render; Re-run refreshes via live backend SSE.
// NOTHING here navigates automatically — every move is a user click.
function useStageSession(stage: string, sessionId?: string | null) {
  const ctx = useSession();
  const sid = sessionId || ctx.sessionId;
  const [data, setData] = useState<any | null>(null);
  const load = () => { if (sid) api.session(sid).then((s: any) => setData(s)).catch(() => {}); };
  useEffect(() => {
    let live = true;
    if (sid) api.session(sid).then((s: any) => live && setData(s)).catch(() => {});
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, ctx.session]);
  return { ...ctx, stageData: data, result: data?.results?.[stage], idea: data?.idea || '', reload: load };
}

function SessionHead({ idea, stage, children }: { idea: string; stage: string; children?: React.ReactNode }) {
  const { runStages, running } = useSession();
  return (
    <div>
      <p className="session-idea">Active research: <strong>{idea}</strong></p>
      <div className="card-bottom" style={{ marginBottom: 12 }}>
        <button className="button secondary" disabled={running} onClick={() => runStages([stage])}>
          {running ? 'Running…' : `Run ${stage}`}
        </button>
        {children}
      </div>
    </div>
  );
}

function SaveButton({ sid, paper }: { sid: string | null; paper: Paper }) {
  const [saved, setSaved] = useState(false);
  if (!sid) return null;
  return (
    <button className="subtle-link" disabled={saved} onClick={async () => { await api.savePaper(sid, paper); setSaved(true); }}>
      {saved ? 'Saved ✓' : 'Save Paper'}
    </button>
  );
}

export function LiteraturePage({ initialQuery, sessionId }: { initialQuery: string; sessionId?: string | null }) {
  const { stageData, result, idea, events, running } = useStageSession('literature', sessionId);
  const sid = sessionId || stageData?.id || null;
  const [q, setQ] = useState(initialQuery);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'empty' | 'error'>('idle');
  const [error, setError] = useState('');
  async function run(query = q) {
    if (!query.trim()) return;
    setStatus('loading'); setError('');
    try {
      const d: any = await api.papersSearch(query.trim());
      setPapers(d.papers || []);
      setStatus((d.papers || []).length ? 'ok' : 'empty');
    } catch (e: any) { setError(String(e.message || e)); setStatus('error'); }
  }
  const stored: Paper[] = result?.papers || [];
  const [cited, setCited] = useState<Paper | null>(null);
  const list = (items: Paper[]) => (
    <>
      {cited && <CitationModal paper={cited} sessionId={sid} onClose={() => setCited(null)} />}
      {items.map((p) => (
        <article key={p.id} className="publication-item">
          <div><div className="eyebrow">{p.year || 'n.d.'} · cited {p.cited_by_count} · {p.is_open_access ? 'open access' : 'closed'}</div>
            <h3>{p.doi ? <a href={`https://doi.org/${p.doi}`}>{p.title || p.id}</a> : (p.title || p.id)}</h3>
            <p className="muted">{(p.abstract || '').slice(0, 220)}</p>
            <div className="tags">{(p.topics || []).map((t) => <span className="tag" key={t}>{t}</span>)}</div>
            <div className="card-bottom">
              <Link className="text-button" href={`/paper?id=${encodeURIComponent(p.id)}${sid ? `&session=${sid}` : ''}`}>Explain</Link>
              <Link className="text-button" href={`/analysis${sid ? `?session=${sid}` : ''}`}>Analyze Paper</Link>
              <button className="subtle-link" onClick={() => setCited(p)}>Cite</button>
              <SaveButton sid={sid} paper={p} />
            </div>
          </div>
        </article>
      ))}
    </>
  );
  return (
    <div className="workspace">
      <span className="eyebrow blue">LITERATURE SEARCH</span>
      <h1>Literature Search</h1>
      {stageData ? (
        <>
          <SessionHead idea={idea} stage="literature" />
          <RunProgress events={events} running={running} />
          {stored.length ? list(stored) : <p className="muted">No papers in this session yet — run the stage.</p>}
        </>
      ) : (
        <>
          <form className="searchbox" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <Search size={20} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. lightweight CNN diabetic retinopathy" aria-label="Literature query" />
            <button className="button primary" type="submit">Search papers</button>
          </form>
          {status === 'loading' && <p className="muted">Searching OpenAlex…</p>}
          {status === 'empty' && <Empty><EmptyHeader><Search size={32} /><EmptyTitle>No relevant research found</EmptyTitle><EmptyDescription>Try a broader query. Nothing is fabricated when retrieval fails.</EmptyDescription></EmptyHeader></Empty>}
          {status === 'error' && <Empty><EmptyHeader><EmptyTitle>Search unavailable</EmptyTitle><EmptyDescription>{error.slice(0, 200)}</EmptyDescription></EmptyHeader></Empty>}
          {status === 'ok' && list(papers)}
        </>
      )}
    </div>
  );
}

export function GapsPage({ initialQuery, sessionId }: { initialQuery: string; sessionId?: string | null }) {
  const { stageData, result, idea, events, running, session } = useStageSession('gaps', sessionId);
  const [q, setQ] = useState(initialQuery);
  const [gaps, setGaps] = useState<any[]>([]);
  const [elab, setElab] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'empty' | 'error'>('idle');
  const [error, setError] = useState('');
  async function run(query = q) {
    if (!query.trim()) return;
    setStatus('loading'); setError('');
    try {
      const d: any = await api.gaps(query.trim());
      setGaps(d.gaps || []); setElab(d.llm_elaboration || '');
      setStatus((d.gaps || []).length ? 'ok' : 'empty');
    } catch (e: any) { setError(String(e.message || e)); setStatus('error'); }
  }
  const stored = result?.gaps || [];
  const direction = stageData?.results?.direction;
  const gapCard = (g: any, i: number, tag: string) => (
    <article key={i} className="faculty-card"><h3>{g.title}</h3><p>{g.description}</p>
      <p className="small muted"><span className="tag">{tag}</span> Confidence: {g.confidence} · Evidence: {JSON.stringify(g.evidence || {}).slice(0, 220)}</p>
      {(g.potential_directions || []).length > 0 && <div className="tags">{g.potential_directions.map((d: string) => <span className="tag warm" key={d}>{d}</span>)}</div>}
    </article>
  );
  const sections = (list: any[]) => (
    <>
      <h2>Research Gaps</h2>
      {list.length ? list.map((g, i) => gapCard(g, i, 'evidence-based')) : <p className="muted">No supporting evidence found — gaps are never invented.</p>}
      <h2>Underexplored Areas</h2>
      {list.filter((g) => g.type === 'combination').map((g, i) => gapCard(g, i, 'evidence-based')) || null}
      {!list.some((g) => g.type === 'combination') && <p className="small muted">No combination gaps in this run.</p>}
      <h2>Coverage & Recency Gaps</h2>
      {list.filter((g) => g.type !== 'combination').map((g, i) => gapCard(g, i, 'evidence-based')) || null}
      <h2>Dataset Gaps</h2>
      <p className="small muted">Dataset-level metadata is unavailable in OpenAlex records; treat topic-sparsity signals above as proxies, not dataset facts.</p>
    </>
  );
  return (
    <div className="workspace">
      <span className="eyebrow blue">GAPS & NOVELTY</span>
      <h1>Gaps & Novelty</h1>
      <p>Potential directions, not guaranteed discoveries. Evidence-based findings are tagged; AI suggestions are labeled as such.</p>
      {stageData ? (
        <>
          <SessionHead idea={idea} stage="gaps" />
          <RunProgress events={events} running={running} />
          {sections(stored)}
          {result?.llm_elaboration && <article className="faculty-card"><h3>AI Suggestion</h3><p>{result.llm_elaboration}</p></article>}
          {direction && (
            <><h2>Potential Research Opportunities</h2>
              <article className="faculty-card"><div className="tags">{(direction.directions || []).map((d: string) => <span className="tag warm" key={d}>{d}</span>)}</div>
                <p className="small muted"><span className="tag">AI-generated</span> Novelty check: {direction.novelty?.verdict} — {direction.novelty?.note}</p>
              </article></>
          )}
          {session && !direction && <p className="small muted">Directions generate with the full pipeline run.</p>}
        </>
      ) : (
        <>
          <form className="searchbox" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <Search size={20} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. lightweight CNNs for medical imaging" aria-label="Gap query" />
            <button className="button primary" type="submit">Find gaps</button>
          </form>
          {status === 'loading' && <p className="muted">Analyzing evidence…</p>}
          {status === 'empty' && <Empty><EmptyHeader><EmptyTitle>No supporting evidence found</EmptyTitle><EmptyDescription>Retrieve literature first; gaps are never invented.</EmptyDescription></EmptyHeader></Empty>}
          {status === 'error' && <Empty><EmptyHeader><EmptyTitle>Analysis unavailable</EmptyTitle><EmptyDescription>{error.slice(0, 200)}</EmptyDescription></EmptyHeader></Empty>}
          {status === 'ok' && <>{sections(gaps)}{elab ? <article className="faculty-card"><h3>AI Suggestion</h3><p>{elab}</p></article> : null}</>}
        </>
      )}
    </div>
  );
}

const PLAN_SECTIONS_VIEW = [
  ['Problem Statement', 'research_question'], ['Research Objectives', 'objective'],
  ['Research Questions', 'research_question'], ['Literature Foundation', 'baseline'],
  ['Methodology', 'proposed_method'], ['Dataset', 'dataset'], ['Experiments', 'experiments'],
  ['Evaluation Metrics', 'evaluation_metrics'], ['Expected Contributions', 'expected_contribution'],
  ['Timeline', 'experiments'], ['Risks', 'potential_risks'],
];

export function PlannerPage({ initialQuery, sessionId }: { initialQuery: string; sessionId?: string | null }) {
  const { stageData, result, idea, events, running, sessionId: ctxSid, reload } = useStageSession('planner', sessionId);
  const sid = sessionId || ctxSid;
  const [q, setQ] = useState(initialQuery);
  const [plan, setPlan] = useState('');
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [error, setError] = useState('');
  async function run(query = q) {
    if (!query.trim()) return;
    setStatus('loading'); setError('');
    try {
      const d: any = await api.plan(query.trim());
      setPlan(d.plan_text || ''); setStatus('ok');
    } catch (e: any) { setError(String(e.message || e)); setStatus('error'); }
  }
  const storedPlan: string = result?.plan_text || '';
  async function saveEdit() {
    if (!sid) return;
    await api.updateSession(sid, { results: { planner: { plan_text: editText } } });
    setEditing(false);
    reload();
  }
  const view = (text: string, canEdit: boolean) => (
    <>
      <div className="tags" style={{ marginBottom: 10 }}>{PLAN_SECTIONS_VIEW.map(([label]) => <span className="tag" key={label}>{label}</span>)}</div>
      {editing ? (
        <><textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={20} style={{ width: '100%' }} aria-label="Edit plan" />
          <div className="card-bottom"><button className="button primary small-btn" onClick={saveEdit}>Save</button>
            <button className="button secondary small-btn" onClick={() => setEditing(false)}>Cancel</button></div></>
      ) : (
        <><article className="faculty-card"><pre style={{ whiteSpace: 'pre-wrap' }}>{text}</pre></article>
          {canEdit && <button className="button secondary small-btn" onClick={() => { setEditText(text); setEditing(true); }}>Edit plan</button>}</>
      )}
      {(result?.evidence || []).length > 0 && <p className="small muted">Literature foundation: {(result.evidence as string[]).slice(0, 6).join(' · ').slice(0, 300)}</p>}
    </>
  );
  return (
    <div className="workspace">
      <span className="eyebrow blue">RESEARCH PLANNER</span>
      <h1>Research Planner</h1>
      {stageData ? (
        <>
          <SessionHead idea={idea} stage="planner" />
          <RunProgress events={events} running={running} />
          {storedPlan ? view(storedPlan, true) : <p className="muted">No plan in this session yet — run the stage.</p>}
          {storedPlan && (
            <div className="two-col" style={{ marginTop: 12 }}>
              <article className="research-card"><h3>Research Notes</h3><NotesPanel sessionId={sid} /></article>
              <article className="research-card"><h3>Export</h3><ExportButtons session={stageData} /></article>
            </div>
          )}
        </>
      ) : (
        <>
          <form className="searchbox" onSubmit={(e) => { e.preventDefault(); run(); }}>
            <Search size={20} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Describe your research idea..." aria-label="Plan idea" />
            <button className="button primary" type="submit">Generate plan</button>
          </form>
          {status === 'loading' && <p className="muted">Grounding plan in retrieved literature…</p>}
          {status === 'error' && <Empty><EmptyHeader><EmptyTitle>Model unavailable</EmptyTitle><EmptyDescription>{error.slice(0, 200)}</EmptyDescription></EmptyHeader></Empty>}
          {status === 'ok' && view(plan, false)}
        </>
      )}
    </div>
  );
}

const STUDIO_SECTIONS = ['Title', 'Abstract', 'Introduction', 'Related Work', 'Methodology', 'Experiments', 'Results', 'Discussion', 'Limitations', 'Conclusion', 'References'];

export function StudioPage({ sessionId }: { sessionId?: string | null }) {
  const { stageData, result, idea, sessionId: ctxSid, reload } = useStageSession('paper', sessionId);
  const sid = sessionId || ctxSid;
  const stored: string = result?.draft || '';
  const evidence: string[] = ((stageData?.results?.literature?.papers) || []).slice(0, 8).map((p: any) => p.title).filter(Boolean);
  const [text, setText] = useState('');
  const [section, setSection] = useState('Abstract');
  const [action, setAction] = useState('improve');
  const [aiOut, setAiOut] = useState('');
  const [aiErr, setAiErr] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (stored) setText(stored); }, [stored]);
  async function save() {
    if (!sid) return;
    await api.updateSession(sid, { results: { paper: { draft: text, status: 'draft' } } });
    reload();
  }
  async function assist() {
    if (!sid || busy) return;
    setBusy(true); setAiErr(''); setAiOut('');
    try {
      const d: any = await api.assist(sid, action, section, text.slice(0, 6000));
      setAiOut(d.text);
    } catch (e: any) {
      setAiErr(String(e.message || e).slice(0, 300));
    } finally { setBusy(false); }
  }
  if (!stageData) {
    return (
      <div className="workspace">
        <span className="eyebrow blue">PAPER STUDIO</span><h1>Paper Studio</h1>
        <p className="muted">Start a research session from the Dashboard to draft from evidence.</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={14} style={{ width: '100%' }} aria-label="Paper draft" />
      </div>
    );
  }
  return (
    <div className="workspace">
      <span className="eyebrow blue">PAPER STUDIO</span><h1>Paper Studio</h1>
      <p className="session-idea">Active research: <strong>{idea}</strong></p>
      <div className="studio-grid">
        <nav className="studio-outline" aria-label="Paper structure">
          {STUDIO_SECTIONS.map((s) => <span key={s} className={section === s ? 'on' : ''} onClick={() => setSection(s)}>{s}</span>)}
        </nav>
        <div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={22} style={{ width: '100%' }} aria-label="Paper draft" />
          <div className="card-bottom"><button className="button primary small-btn" onClick={save}>Save draft</button><ExportButtons session={stageData} /></div>
        </div>
        <aside className="studio-ai">
          <h3>AI writing assistant</h3>
          <div className="field"><label>Section</label>
            <select value={section} onChange={(e) => setSection(e.target.value)}>{STUDIO_SECTIONS.map((s) => <option key={s}>{s}</option>)}</select></div>
          <div className="field"><label>Action</label>
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="generate">Generate section</option><option value="improve">Improve writing</option>
              <option value="summarize">Summarize</option><option value="expand">Expand</option><option value="rewrite">Rewrite</option>
            </select></div>
          <button className="button primary small-btn" disabled={busy} onClick={assist}>{busy ? 'Working…' : 'Run'}</button>
          {aiErr && <p className="small muted">Assistant unavailable: {aiErr}</p>}
          {aiOut && <article className="research-card"><pre style={{ whiteSpace: 'pre-wrap' }}>{aiOut}</pre></article>}
          <h3>Citations (session evidence)</h3>
          {evidence.length ? evidence.map((t, i) => <p key={i} className="small muted rail-item">[{i + 1}] {t}</p>) : <p className="small muted">No evidence yet.</p>}
          <h3>IEEE export</h3>
          <p className="small muted">Formatter integration pending — the DOCX formatter was not found in the repo.</p>
        </aside>
      </div>
    </div>
  );
}
