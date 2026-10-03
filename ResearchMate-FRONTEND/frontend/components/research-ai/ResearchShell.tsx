'use client';
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, ScanSearch, BookOpen, ChartNoAxesCombined, Lightbulb,
  FlaskConical, FileText, FolderKanban, Bookmark, FileEdit, History,
  Settings as SettingsIcon, Cpu, Menu, X, Pencil,
} from 'lucide-react';
import { SessionProvider, useSession, withSession } from '@/lib/session';
import WorkflowIndicator from './WorkflowIndicator';
import { api } from '@/lib/api';

const MAIN_NAV = [
  { label: 'Dashboard', href: '/app', Icon: LayoutDashboard },
  { label: 'Faculty Discovery', href: '/faculty', Icon: ScanSearch },
  { label: 'Literature Search', href: '/literature', Icon: BookOpen },
  { label: 'Research Analysis', href: '/analysis', Icon: ChartNoAxesCombined },
  { label: 'Gaps & Novelty', href: '/gaps', Icon: Lightbulb },
  { label: 'Research Planner', href: '/planner', Icon: FlaskConical },
  { label: 'Paper Studio', href: '/paper-studio', Icon: FileText },
];
const MY_RESEARCH = [
  { label: 'Projects', href: '/projects', Icon: FolderKanban },
  { label: 'Saved Papers', href: '/saved', Icon: Bookmark },
  { label: 'Drafts', href: '/drafts', Icon: FileEdit },
  { label: 'Research History', href: '/history', Icon: History },
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
  const { session, sessionId, selectSession } = useSession();
  const [open, setOpen] = useState(false);

  // ?session= links select the session without navigating away.
  useEffect(() => {
    try {
      const sid = new URLSearchParams(window.location.search).get('session');
      if (sid && sid !== sessionId) selectSession(sid);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const link = (href: string, label: string, Icon: any) => (
    <Link key={href} href={withSession(href, sessionId)} className={path === href ? 'active' : ''} onClick={() => setOpen(false)}>
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
        {session && <p className="research-idea" title={session.idea}>{session.idea}</p>}
        <nav aria-label="Research sections">{MAIN_NAV.map((n) => link(n.href, n.label, n.Icon))}</nav>
        <p className="side-head">MY RESEARCH</p>
        <nav aria-label="My research">{MY_RESEARCH.map((n) => link(n.href, n.label, n.Icon))}</nav>
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
