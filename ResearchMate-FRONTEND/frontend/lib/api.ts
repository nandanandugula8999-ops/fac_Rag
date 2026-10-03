// Research AI backend client. Frontend never holds GROQ_API_KEY or any secret;
// all LLM calls go through the FastAPI backend (server-side key only).
const BASE =
  (typeof process !== "undefined" && (process.env as any)?.NEXT_PUBLIC_BACKEND_URL) ||
  "http://127.0.0.1:8000";

async function req(path: string, init?: RequestInit): Promise<any> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Backend ${res.status}: ${text.slice(0, 300) || res.statusText}`);
  }
  return res.json();
}

export const api = {
  base: BASE,
  providers: () => req("/api/ai/providers"),
  facultySearch: (query: string, top_k = 10) =>
    req("/api/faculty/search", { method: "POST", body: JSON.stringify({ query, top_k }) }),
  papersSearch: (query: string, top_k = 10) =>
    req(`/api/papers/search?query=${encodeURIComponent(query)}&top_k=${top_k}`),
  gaps: (query: string) =>
    req("/api/analysis/gaps", { method: "POST", body: JSON.stringify({ query }) }),
  novelty: (query: string) =>
    req("/api/analysis/novelty", { method: "POST", body: JSON.stringify({ query }) }),
  plan: (query: string) =>
    req("/api/planner/generate", { method: "POST", body: JSON.stringify({ query }) }),
  projects: () => req("/api/projects"),
  createProject: (title: string, idea: string) =>
    req("/api/projects", { method: "POST", body: JSON.stringify({ title, idea }) }),
  createSession: (idea: string) =>
    req("/api/sessions", { method: "POST", body: JSON.stringify({ idea }) }),
  sessions: () => req("/api/sessions"),
  session: (id: string) => req(`/api/sessions/${encodeURIComponent(id)}`),
  updateSession: (id: string, patch: { idea?: string; results?: any }) =>
    req(`/api/sessions/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(patch) }),
  savePaper: (id: string, paper: any) =>
    req(`/api/sessions/${encodeURIComponent(id)}/papers`, { method: 'POST', body: JSON.stringify(paper) }),
  removePaper: (id: string, pid: string) =>
    req(`/api/sessions/${encodeURIComponent(id)}/papers/${encodeURIComponent(pid)}`, { method: 'DELETE' }),
  assist: (id: string, action: string, section: string, text: string) =>
    req(`/api/sessions/${encodeURIComponent(id)}/assist`, { method: 'POST', body: JSON.stringify({ action, section, text }) }),
  sessionRunUrl: (id: string, stages: string[]) =>
    `${BASE}/api/sessions/${encodeURIComponent(id)}/run?stages=${stages.join(",")}`,
};

export type Gap = {
  title: string;
  description: string;
  confidence: string;
  type: string;
  evidence?: any;
  potential_directions?: string[];
};

export type Paper = {
  id: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  citation_url: string | null;
  abstract: string | null;
  topics: string[];
  cited_by_count: number;
  is_open_access: boolean;
};
