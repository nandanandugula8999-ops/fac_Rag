'use client';
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, PlusCircle, FolderKanban, FileStack, Bookmark, Layers,
  ChartNoAxesCombined, History, Settings as SettingsIcon, Cpu, Menu, X, Pencil,
  ScanSearch, BookOpen, Lightbulb, FlaskConical, FileText, Search,
} from 'lucide-react';
import { SessionProvider, useSession, withSession } from '@/lib/session';
import WorkflowIndicator from './WorkflowIndicator';
import { readNotes } from './Widgets';
import { api } from '@/lib/api';

const MODULES = [
  { label: 'Faculty Discovery', href: '/faculty', Icon: ScanSearch },
  { label: 'Literature Search', href: '/literature', Icon: BookOpen },
  { label: 'Research Analysis', href: '/analysis', Icon: ChartNoAxesCombined },
  { label: 'Gaps & Novelty', href: '/gaps', Icon: Lightbulb },
  { label: 'Research Planner', href: '/planner', Icon: FlaskConical },
  { label: 'Paper Studio', href: '/paper-studio', Icon: FileText },
];
const LIBRARY = [
  { label: 'Dashboard', href: '/app', Icon: LayoutDashboard },
  { label: 'New Research', href: '/app?new=1', Icon: PlusCircle },
  { label: 'My Research', href: '/projects', Icon: FolderKanban },
  { label: 'Documents', href: '/documents', Icon: FileStack },
  { label: 'Saved Sources', href: '/saved', Icon: Bookmark },
  { label: 'Collections', href: '/collections', Icon: Layers },
  { label: 'Analytics', href: '/analytics', Icon: ChartNoAxesCombined },
  { label: 'History', href: '/history', Icon: History },
];

function ProviderBadge() {
  const [label, setLabel] = useState('checking…');
  const [ok, setOk] = useState(false);
  useEffect(() => {
    let live = true;
    api.providers()
      .then((d: any) => {
        if (!live) return;
        const g = (d.providers || []).find((p: any) => p.name === 'groq');
        // Only claim Groq when the backend reports it configured; never show Ollama as active.
        if (g?.available) { setLabel(`Groq · ${g.model}`); setOk(true); }
        else setLabel('Offline evidence mode');
      })
      .catch(() => live && setLabel('Backend unreachable'));
    return () => { live = false; };
  }, []);
  return <span className={`provider-badge ${ok ? 'on' : ''}`}><Cpu size={13} />{label}</span>;
}

// Global search over REAL local data: sessions, saved papers, notes.
function GlobalSearch({ onNav }: { onNav: () => void }) {
  const [q, setQ] = useState('');
  const [out, setOut] = useState<any[]>([]);
  useEffect(() => {
    const query = q.trim().toLowerCase();
    if (query.length < 2) { setOut([]); return; }
    let live = true;
    api.sessions().then((d: any) => {
      if (!live) return;
      const hits: any[] = [];
      (d.sessions || []).forEach((s: any) => {
        if ((s.idea || '').toLowerCase().includes(query)) hits.push({ kind: 'Research', text: s.idea, href: `/app?session=${s.id}` });
        ((s.results?.saved_papers?.papers) || []).forEach((p: any) => {
          if ((p.title || '').toLowerCase().includes(query)) hits.push({ kind: 'Source', text: p.title, href: `/saved` });
        });
        readNotes(s.id).forEach((n: any) => {
          if ((n.text || '').toLowerCase().includes(query)) hits.push({ kind: 'Note', text: n.text.slice(0, 80), href: `/analysis?session=${s.id}` });
        });
      });
      setOut(hits.slice(0, 8));
    }).catch(() => {});
    return () => { live = false; };
  }, [q]);
  return (
    <div className="side-search">
      <Search size={14} />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search research, sources, notes…" aria-label="Global search" />
      {out.length > 0 && (
        <div className="side-results">
          {out.map((h, i) => (
            <Link key={i} href={h.href} onClick={() => { setQ(''); setOut([]); onNav(); }}>
              <strong>{h.kind}</strong> · {h.text.slice(0, 70)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function ActiveResearchBar() {
  const { session, sessionId, refresh } = useSession();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  if (!session) return null;
  async function save() {
    if (!draft.trim() || !sessionId) { setEditing(false); return; }
    try { await api.updateSession(sessionId, { idea: draft.trim() }); await refresh(); } catch {}
    setEditing(false);
  }
  return (
    <div className="active-bar" aria-label="Active research context">
      <span className="eyebrow blue">ACTIVE RESEARCH</span>
      {editing ? (
        <span className="active-edit">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Edit research context" maxLength={500} />
          <button className="button primary small-btn" onClick={save}>Save</button>
          <button className="button secondary small-btn" onClick={() => setEditing(false)}>Cancel</button>
        </span>
      ) : (
        <span className="active-idea">{session.idea}</span>
      )}
      {!editing && (
        <span className="active-actions">
          <button className="subtle-link" onClick={() => { setDraft(session.idea); setEditing(true); }}><Pencil size={13} /> Edit</button>
          <Link className="subtle-link" href="/app">Dashboard</Link>
        </span>
      )}
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || '/app';
  const { session, sessionId, selectSession, clearSession } = useSession();
  const [open, setOpen] = useState(false);

  // ?session= / ?new=1 links act without navigating away.
  useEffect(() => {
    try {
      const sp = new URLSearchParams(window.location.search);
      if (sp.get('new') === '1') { clearSession(); return; }
      const sid = sp.get('session');
      if (sid && sid !== sessionId) selectSession(sid);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const link = (href: string, label: string, Icon: any) => (
    <Link key={href + label} href={withSession(href.split('?')[0], href.includes('new=1') ? null : sessionId) + (href.includes('new=1') ? '?new=1' : '')}
      className={path === href.split('?')[0] && !href.includes('new=1') ? 'active' : ''} onClick={() => setOpen(false)}>
      <Icon size={16} />{label}
    </Link>
  );
  return (
    <div className="research-shell">
      <button className="side-toggle" aria-label="Toggle navigation" onClick={() => setOpen((v) => !v)}>
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside className={`research-side ${open ? 'open' : ''}`}>
        <Link href="/app" className="research-brand" onClick={() => setOpen(false)}>
          Research AI<small>From Ideas to Impact</small>
        </Link>
        <GlobalSearch onNav={() => setOpen(false)} />
        {session && <p className="research-idea" title={session.idea}>{session.idea}</p>}
        <p className="side-head">RESEARCH</p>
        <nav aria-label="Research modules">{MODULES.map((n) => link(n.href, n.label, n.Icon))}</nav>
        <p className="side-head">MY RESEARCH</p>
        <nav aria-label="Library">{LIBRARY.map((n) => link(n.href, n.label, n.Icon))}</nav>
        <div className="side-foot">
          <nav aria-label="System">
            <Link href="/settings" className={path === '/settings' ? 'active' : ''} onClick={() => setOpen(false)}>
              <SettingsIcon size={16} />Settings
            </Link>
          </nav>
          <ProviderBadge />
        </div>
      </aside>
      <div className="research-main">
        {path !== '/app' && session && <ActiveResearchBar />}
        {session && <WorkflowIndicator status={session.stage_status} sessionId={sessionId} />}
        {children}
      </div>
    </div>
  );
}

// Wraps every research page: sidebar, session context, workflow indicator.
export default function ResearchShell({ children }: { children: React.ReactNode }) {
  return <SessionProvider><Shell>{children}</Shell></SessionProvider>;
}
