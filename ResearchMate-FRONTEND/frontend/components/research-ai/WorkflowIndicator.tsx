'use client';
import Link from 'next/link';
import { Check } from 'lucide-react';
import { STAGES, withSession } from '@/lib/session';

// Persistent 01->08 indicator. Completed = check, active = pulsing dot,
// pending = number. Users can revisit completed stages; data lives in session.
export default function WorkflowIndicator({ status, sessionId }: { status: Record<string, string>; sessionId: string | null }) {
  return (
    <nav className="workflow" aria-label="Research workflow">
      {STAGES.map((s, i) => {
        const st = status?.[s.key] || 'pending';
        return (
          <span key={s.key} className="workflow-step-wrap">
            <Link href={withSession(s.href, sessionId)} className={`workflow-step ${st}`}>
              <span className="workflow-n">
                {st === 'done' ? <Check size={13} /> : st === 'active' ? <span className="pulse" /> : st === 'error' ? '!' : s.n}
              </span>
              <span>{s.label}</span>
            </Link>
            {i < STAGES.length - 1 && <span className="workflow-line" />}
          </span>
        );
      })}
    </nav>
  );
}
