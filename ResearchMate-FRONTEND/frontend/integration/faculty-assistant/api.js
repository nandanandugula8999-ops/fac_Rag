/** HTTP adapter only. All discovery, ranking, scoring and verification stay in FastAPI. */
export class FacultyApiError extends Error {
  constructor(message, code) { super(message); this.name = 'FacultyApiError'; this.code = code; }
}
export function safeSourceUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : null; } catch { return null; }
}
export function doiUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const direct = safeSourceUrl(value);
  if (direct) return direct;
  const doi = value.replace(/^doi:\s*/i, '').trim();
  return /^10\.\d{4,9}\/.+/.test(doi) ? `https://doi.org/${doi}` : null;
}
export function validateResponse(payload) {
  if (!payload || typeof payload !== 'object' || !['ok', 'insufficient_evidence'].includes(payload.status) || !Array.isArray(payload.matches)) {
    throw new FacultyApiError('The backend returned an unexpected response format.', 'invalid_response');
  }
  if (!['live-openalex', 'datalake'].includes(payload.corpus_source)) {
    throw new FacultyApiError('The backend is not serving a real OpenAlex or data-lake corpus. Fixture results are not displayed.', 'non_live_source');
  }
  if (payload.status === 'insufficient_evidence') return { ...payload, matches: [] };
  for (const match of payload.matches) {
    if (!match || typeof match.faculty_id !== 'string' || typeof match.faculty_name !== 'string' || typeof match.score !== 'number' || !Number.isFinite(match.score)) {
      throw new FacultyApiError('The backend returned an incomplete faculty record.', 'invalid_response');
    }
    for (const key of ['institutions', 'stated_topics', 'matched_topics', 'supporting_publications', 'evidence', 'signals']) {
      if (match[key] !== undefined && !Array.isArray(match[key])) throw new FacultyApiError(`Invalid ${key} in backend response.`, 'invalid_response');
    }
  }
  return payload;
}
export function createFacultyClient(baseUrl, { fetchImpl = globalThis.fetch, timeoutMs = 180000 } = {}) {
  let url;
  try { url = new URL(baseUrl); } catch { throw new FacultyApiError('Set VITE_API_BASE_URL to your FastAPI server address.', 'configuration'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new FacultyApiError('Use an HTTP(S) backend address without embedded credentials, query parameters, or fragments.', 'configuration');
  const base = url.href.replace(/\/$/, '');
  return {
    async search(query, { topK = 10, signal } = {}) {
      if (typeof query !== 'string' || !query.trim() || query.trim().length > 500) throw new FacultyApiError('Enter a research topic between 1 and 500 characters.', 'validation');
      if (!Number.isInteger(topK) || topK < 1 || topK > 50) throw new FacultyApiError('top_k must be between 1 and 50.', 'validation');
      const controller = new AbortController();
      let timedOut = false;
      const abort = () => controller.abort();
      if (signal?.aborted) controller.abort();
      signal?.addEventListener('abort', abort, { once: true });
      const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
      try {
        const response = await fetchImpl(`${base}/api/faculty/search`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: query.trim(), top_k: topK }), signal: controller.signal, credentials: 'omit' });
        if (!response.ok) throw new FacultyApiError(response.status === 422 ? 'The backend rejected this search. Check your query.' : `The backend returned HTTP ${response.status}. Please retry.`, `http_${response.status}`);
        return validateResponse(await response.json());
      } catch (error) {
        if (signal?.aborted) throw error;
        if (timedOut) throw new FacultyApiError('The backend search timed out. Try again or check the backend logs.', 'timeout');
        if (error instanceof FacultyApiError) throw error;
        if (error instanceof SyntaxError) throw new FacultyApiError('The backend returned invalid JSON.', 'invalid_response');
        throw new FacultyApiError('Cannot reach the FastAPI backend. Check that it is running and that VITE_API_BASE_URL and CORS allow this connection.', 'network');
      } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
    }
  };
}
