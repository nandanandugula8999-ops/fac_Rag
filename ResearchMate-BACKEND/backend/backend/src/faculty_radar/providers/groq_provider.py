"""Groq cloud provider (server-side only).

- Reads GROQ_API_KEY from backend env: FR_GROQ__API_KEY (never frontend,
  never VITE_/NEXT_PUBLIC_).
- Default model is a Llama model; override via FR_GROQ__MODEL.
- Uses Groq OpenAI-compatible endpoint: POST {base_url}/chat/completions.
- Failures raise GroqError with a safe message (key redacted); callers fall
  back to extractive evidence-only output, never to invented content.
"""

from __future__ import annotations

import httpx

from faculty_radar.config import Settings, get_logger, get_settings

logger = get_logger(__name__)


class GroqError(RuntimeError):
    """Groq API unavailable or misconfigured."""


class GroqProvider:
    name = "groq"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def model_id(self) -> str:
        return self.settings.groq.model

    def available(self) -> bool:
        return bool((self.settings.groq.api_key or "").strip())

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        groq = self.settings.groq
        api_key = (groq.api_key or "").strip()
        if not api_key:
            raise GroqError(
                "Groq provider selected but FR_GROQ__API_KEY is not configured. "
                "Set it in the backend .env; the key must never appear in frontend code."
            )
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": groq.model,
            "messages": messages,
            "temperature": groq.temperature if temperature is None else temperature,
            "max_tokens": groq.max_tokens if max_tokens is None else max_tokens,
        }
        url = f"{groq.base_url.rstrip('/')}/chat/completions"
        try:
            with httpx.Client(timeout=groq.timeout_seconds) as client:
                resp = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except Exception as exc:
            raise GroqError(f"Groq request failed: {exc}") from exc
        if resp.status_code in (401, 403):
            raise GroqError("Groq rejected the API key (401/403). Check FR_GROQ__API_KEY.")
        if resp.status_code == 429:
            raise GroqError("Groq rate limit exceeded (429). Retry later or switch provider.")
        if resp.is_error:
            # Never echo the key; truncate server message for safety.
            detail = (resp.text or "")[:300]
            raise GroqError(f"Groq error {resp.status_code}: {detail}")
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise GroqError(f"Groq returned an unexpected payload: {exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise GroqError("Groq returned an empty completion.")
        logger.debug("groq completion complete", extra={"model": groq.model})
        return text.strip()

    def stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        """Yield text deltas via Groq SSE. Raises GroqError like generate()."""
        import json as _json

        groq = self.settings.groq
        api_key = (groq.api_key or "").strip()
        if not api_key:
            raise GroqError(
                "Groq provider selected but FR_GROQ__API_KEY is not configured. "
                "Set it in the backend .env; the key must never appear in frontend code."
            )
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": groq.model,
            "messages": messages,
            "temperature": groq.temperature if temperature is None else temperature,
            "max_tokens": groq.max_tokens if max_tokens is None else max_tokens,
            "stream": True,
        }
        url = f"{groq.base_url.rstrip('/')}/chat/completions"
        try:
            with httpx.stream(
                "POST",
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=groq.timeout_seconds,
            ) as resp:
                if resp.status_code in (401, 403):
                    raise GroqError("Groq rejected the API key (401/403). Check FR_GROQ__API_KEY.")
                if resp.status_code == 429:
                    raise GroqError("Groq rate limit exceeded (429). Retry later or switch provider.")
                if resp.is_error:
                    raise GroqError(f"Groq error {resp.status_code}: {resp.read().decode()[:300]}")
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data)
                        delta = chunk["choices"][0].get("delta", {}).get("content") or ""
                    except Exception:
                        continue
                    if delta:
                        yield delta
        except GroqError:
            raise
        except Exception as exc:
            raise GroqError(f"Groq stream failed: {exc}") from exc
