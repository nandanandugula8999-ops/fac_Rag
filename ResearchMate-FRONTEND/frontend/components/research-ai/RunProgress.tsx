'use client';
import { Check, Loader2, Circle, AlertTriangle } from 'lucide-react';
import type { SseEvent } from '@/lib/session';

// LIVE progress: every row comes from a real backend SSE event.
// Done rows show check + real counts; the in-flight row shows active;
// nothing is on a timer and nothing is simulated.
export default function RunProgress({ events, running }: { events: SseEvent[]; running: boolean }) {
  const steps = events.filter((e) => e.event === 'progress' || e.event === 'stage_error');
  const doneStages = new Set(events.filter((e) => e.event === 'stage_done').map((e) => e.stage));
  if (!steps.length && !running) return null;
  return (
    <div className="run-progress" aria-live="polite">
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const active = running && last && !doneStages.has(s.stage);
        return (
          <div key={i} className={`run-step ${active ? 'active' : 'done'}`}>
            {active ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
            <span>{s.message}</span>
          </div>
        );
      })}
      {events.some((e) => e.event === 'stage_error') && (
        <div className="run-step error">
          <AlertTriangle size={14} />
          <span>{events.filter((e) => e.event === 'stage_error').map((e) => e.message).join(' · ')}</span>
        </div>
      )}
      {!running && steps.length > 0 && <div className="run-step idle"><Circle size={12} /><span>Run complete — results saved to this session.</span></div>}
    </div>
  );
}
