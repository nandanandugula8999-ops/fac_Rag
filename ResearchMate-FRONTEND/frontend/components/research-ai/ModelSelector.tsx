'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

// Model selector for the dashboard research input (plan.md section 28).
// Lists only configured/available models from GET /api/ai/providers.
// No API keys here — selection is sent to the backend, key stays server-side.
export default function ModelSelector({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [providers, setProviders] = useState<any[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    api.providers().then((d: any) => live && setProviders(d.providers || [])).catch((e) => live && setError(String(e.message || e)));
    return () => { live = false; };
  }, []);
  if (error) return <p className="small muted">Model list unavailable ({error.slice(0, 80)}). Using offline evidence mode.</p>;
  if (!providers.length) return <p className="small muted">Loading models…</p>;
  return (
    <div className="field">
      <label htmlFor="ai-model">AI Model</label>
      <select id="ai-model" className="filter-select" value={value} onChange={(e) => onChange(e.target.value)}>
        {providers.map((p) => (
          <option key={p.name} value={p.name} disabled={!p.available}>
            {p.name === 'groq' ? `Groq — ${p.model}` : p.name === 'ollama' ? `Ollama — coming soon` : `Offline — ${p.model}`}
            {!p.available ? ' (not configured)' : ''}
          </option>
        ))}
      </select>
      <p className="small muted">Groq key lives on the backend only. Ollama stub reserved for later.</p>
    </div>
  );
}
