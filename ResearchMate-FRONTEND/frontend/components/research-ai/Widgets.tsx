'use client';
import { useEffect, useState } from 'react';
import { X, Download, Bookmark } from 'lucide-react';
import { api } from '@/lib/api';

// ---- Citation modal: title, author/year, passage, source links, save ----
export function CitationModal({ paper, sessionId, onClose, onSaved }: {
  paper: any; sessionId: string | null; onClose: () => void; onSaved?: () => void;
}) {
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', fn);
    return () => window.removeEventListener('keydown', fn);
  }, [onClose]);
  return (
    <div className="modal-back" onClick={onClose} role="dialog" aria-modal="true" aria-label="Citation detail">
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="Close"><X size={18} /></button>
        <span className="eyebrow blue">CITATION</span>
        <h3>{paper.title || paper.id}</h3>
        <p className="small muted">
          {paper.year || 'n.d.'}
          {paper.doi ? <> · DOI: <a href={`https://doi.org/${paper.doi}`}>{paper.doi}</a></> : ' · No DOI in record'}
          {typeof paper.cited_by_count === 'number' && <> · Cited by {paper.cited_by_count}</>}
        </p>
        {(paper.abstract || paper.passage) && (
          <><h3>Relevant passage</h3><blockquote className="cite-passage">{(paper.abstract || paper.passage || '').slice(0, 600)}</blockquote>
          <p className="small muted">Excerpt from the retrieved record — verify in the full text.</p></>
        )}
        <div className="card-bottom">
          {paper.doi && <a className="button secondary small-btn" href={`https://doi.org/${paper.doi}`}>Open source</a>}
          {paper.citation_url && !paper.doi && <a className="button secondary small-btn" href={paper.citation_url}>Open source</a>}
          {sessionId && !saved && (
            <button className="button secondary small-btn" onClick={async () => { await api.savePaper(sessionId, paper); setSaved(true); onSaved?.(); }}>
              <Bookmark size={13} /> Save source
            </button>
          )}
          {saved && <span className="small muted">Saved ✓</span>}
        </div>
      </div>
    </div>
  );
}

// ---- Research notes: per-session, stored locally (real user data) ----
type Note = { id: string; text: string; at: string };
function loadNotes(sid: string): Note[] {
  try { return JSON.parse(localStorage.getItem(`research-notes:${sid}`) || '[]'); } catch { return []; }
}
export function readNotes(sid: string): Note[] { return loadNotes(sid); }

export function NotesPanel({ sessionId }: { sessionId: string | null }) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [text, setText] = useState('');
  useEffect(() => { if (sessionId) setNotes(loadNotes(sessionId)); else setNotes([]); }, [sessionId]);
  if (!sessionId) return <p className="small muted">Start a session to take notes.</p>;
  function add() {
    if (!text.trim() || !sessionId) return;
    const n = { id: Math.random().toString(36).slice(2, 10), text: text.trim(), at: new Date().toISOString() };
    const next = [n, ...notes];
    setNotes(next);
    try { localStorage.setItem(`research-notes:${sessionId}`, JSON.stringify(next)); } catch {}
    setText('');
  }
  function del(id: string) {
    if (!sessionId) return;
    const next = notes.filter((n) => n.id !== id);
    setNotes(next);
    try { localStorage.setItem(`research-notes:${sessionId}`, JSON.stringify(next)); } catch {}
  }
  return (
    <div>
      <div className="note-add">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a research note…" aria-label="New note" maxLength={500}
          onKeyDown={(e) => { if (e.key === 'Enter') add(); }} />
        <button className="button secondary small-btn" onClick={add}>Add</button>
      </div>
      {notes.length ? notes.map((n) => (
        <div key={n.id} className="note-item">
          <p>{n.text}</p>
          <p className="small muted">{new Date(n.at).toLocaleString()} · <button className="subtle-link" onClick={() => del(n.id)}>Delete</button></p>
        </div>
      )) : <p className="small muted">No notes yet.</p>}
    </div>
  );
}

// ---- Export: Markdown + JSON generated from REAL session data ----
export function sessionMarkdown(s: any): string {
  const L: string[] = [`# Research Report`, ``, `**Idea:** ${s.idea}`, ``];
  const papers = s.results?.literature?.papers || [];
  const gaps = s.results?.gaps?.gaps || [];
  const faculty = s.results?.faculty?.matches || [];
  const plan = s.results?.planner?.plan_text || '';
  L.push(`## Literature (${papers.length})`);
  papers.forEach((p: any, i: number) => L.push(`${i + 1}. ${p.title || p.id} (${p.year || 'n.d.'})${p.doi ? ` — doi:${p.doi}` : ''}`));
  L.push(``, `## Faculty (${faculty.length})`);
  faculty.forEach((f: any) => L.push(`- ${f.faculty_name} — ${Math.round((f.score || 0) * 100)}% [${f.expertise_type}]`));
  L.push(``, `## Gaps (${gaps.length})`);
  gaps.forEach((g: any) => L.push(`- **${g.title}** (${g.confidence}): ${g.description}`));
  if (plan) L.push(``, `## Plan`, ``, plan);
  return L.join('\n');
}

export function ExportButtons({ session }: { session: any | null }) {
  if (!session) return null;
  const dl = (name: string, text: string, type: string) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  const slug = (session.idea || 'research').slice(0, 40).replace(/[^a-z0-9]+/gi, '-');
  return (
    <span className="export-row">
      <button className="button secondary small-btn" onClick={() => dl(`${slug}.md`, sessionMarkdown(session), 'text/markdown')}>
        <Download size={13} /> Export Markdown
      </button>
      <button className="button secondary small-btn" onClick={() => dl(`${slug}.json`, JSON.stringify(session, null, 2), 'application/json')}>
        <Download size={13} /> Export JSON
      </button>
    </span>
  );
}
