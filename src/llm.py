"""Provider-agnostic LLM client. Pick a backend with VIBEMATCH_PROVIDER=gemini|anthropic.

Both backends expose the same two methods, so the rest of the app never imports a vendor SDK:
  structured(system, user, schema) -> pydantic instance
  generate(system, user)           -> str
"""

from __future__ import annotations

import os

# Cheapest Gemini text model that is still open to new accounts (free tier; $0.25 in / $1.50 out
# per 1M tokens). gemini-2.5-flash-lite is cheaper on paper but the API now rejects it for new
# users. Override via VIBEMATCH_GEMINI_MODEL.
GEMINI_MODEL = os.getenv("VIBEMATCH_GEMINI_MODEL", "gemini-3.1-flash-lite")


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str = GEMINI_MODEL):
        from google import genai
        self._client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.model = model

    def structured(self, system: str, user: str, schema):
        from google.genai import types
        resp = self._client.models.generate_content(
            model=self.model, contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system, response_mime_type="application/json",
                response_schema=schema, temperature=0),
        )
        if resp.parsed is None:
            raise RuntimeError("Gemini returned no parsable output")
        return resp.parsed

    def generate(self, system: str, user: str) -> str:
        from google.genai import types
        resp = self._client.models.generate_content(
            model=self.model, contents=user,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
        )
        return (resp.text or "").strip()


class AnthropicClient:
    def __init__(self, parser_model: str = "claude-haiku-5-5", explainer_model: str = "claude-sonnet-5-5"):
        import anthropic
        self._client = anthropic.Anthropic()
        self.parser_model, self.explainer_model = parser_model, explainer_model

    def structured(self, system: str, user: str, schema):
        r = self._client.messages.parse(
            model=self.parser_model, max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}], output_format=schema,
            output_config={"effort": "low"})
        if r.stop_reason == "refusal" or r.parsed_output is None:
            raise RuntimeError("declined")
        return r.parsed_output

    def generate(self, system: str, user: str) -> str:
        r = self._client.messages.create(
            model=self.explainer_model, max_tokens=2000, system=system,
            messages=[{"role": "user", "content": user}], output_config={"effort": "low"})
        if r.stop_reason == "refusal":
            raise RuntimeError("declined")
        return "".join(b.text for b in r.content if b.type == "text").strip()


def get_client():
    """Build the configured backend, or raise if it has no credentials (callers fall back)."""
    provider = os.getenv("VIBEMATCH_PROVIDER", "gemini").lower()
    return AnthropicClient() if provider == "anthropic" else GeminiClient()
