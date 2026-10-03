'use client';
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

// ONE research idea -> ONE persistent session shared by all stages.
// Stages read session.results; the idea is typed once on the Dashboard.
export const STAGES = [
  { key: 'idea', n: '01', label: 'Idea', href: '/app' },
  { key: 'faculty', n: '02', label: 'Faculty', href: '/faculty' },
  { key: 'literature', n: '03', label: 'Literature', href: '/literature' },
  { key: 'analysis', n: '04', label: 'Analysis', href: '/analysis' },
  { key: 'gaps', n: '05', label: 'Gaps', href: '/gaps' },
  { key: 'direction', n: '06', label: 'Direction', href: '/gaps' },
  { key: 'planner', n: '07', label: 'Planner', href: '/planner' },
  { key: 'paper', n: '08', label: 'Paper', href: '/paper-studio' },
] as const;

export type SseEvent = { event: string; stage: string; message: string; [k: string]: any };

type Ctx = {
  sessionId: string | null;
  session: any | null;
  events: SseEvent[];
  running: boolean;
  createSession: (idea: string) => Promise<any>;
  selectSession: (id: string) => Promise<void>;
  clearSession: () => void;
  refresh: () => Promise<void>;
  runStages: (stages: string[], onEvent?: (e: SseEvent) => void) => Promise<void>;
};

const SessionCtx = createContext<Ctx | null>(null);
const LS_KEY = 'research-session-id';

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<any | null>(null);
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [running, setRunning] = useState(false);
  const runRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    try {
      const s: any = await api.session(sessionId);
      setSession(s);
    } catch {}
  }, [sessionId]);

  const selectSession = useCallback(async (id: string) => {
    setSessionId(id);
    setEvents([]);
    try { localStorage.setItem(LS_KEY, id); } catch {}
    try {
      const s: any = await api.session(id);
      setSession(s);
    } catch { setSession(null); }
  }, []);

  useEffect(() => {
    try {
      const last = localStorage.getItem(LS_KEY);
      if (last) selectSession(last);
    } catch {}
  }, [selectSession]);

  const createSession = useCallback(async (idea: string) => {
    const s: any = await api.createSession(idea);
    setSessionId(s.id);
    setSession(s);
    setEvents([]);
    try { localStorage.setItem(LS_KEY, s.id); } catch {}
    return s;
  }, []);

  const clearSession = useCallback(() => {
    setSessionId(null);
    setSession(null);
    setEvents([]);
    try { localStorage.removeItem(LS_KEY); } catch {}
  }, []);

  // Streams REAL backend progress (fetch reader over SSE endpoint).
  const runStages = useCallback(async (stages: string[], onEvent?: (e: SseEvent) => void) => {
    if (!sessionId || runRef.current) return;
    runRef.current = true;
    setRunning(true);
    try {
      const res = await fetch(api.sessionRunUrl(sessionId, stages));
      if (!res.ok || !res.body) throw new Error(`Backend ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      const push = (e: SseEvent) => {
        setEvents((prev) => [...prev.slice(-200), e]);
        onEvent?.(e);
      };
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() || '';
        for (const p of parts) {
          const line = p.split('\n').find((l) => l.startsWith('data:'));
          if (!line) continue;
          try { push(JSON.parse(line.slice(5)) as SseEvent); } catch {}
        }
      }
    } finally {
      runRef.current = false;
      setRunning(false);
      await refresh();
    }
  }, [sessionId, refresh]);

  return (
    <SessionCtx.Provider value={{ sessionId, session, events, running, createSession, selectSession, clearSession, refresh, runStages }}>
      {children}
    </SessionCtx.Provider>
  );
}

export function useSession() {
  const c = useContext(SessionCtx);
  if (!c) throw new Error('useSession must be used inside SessionProvider');
  return c;
}

export function withSession(href: string, sessionId: string | null) {
  if (!sessionId) return href;
  return `${href}?session=${encodeURIComponent(sessionId)}`;
}
