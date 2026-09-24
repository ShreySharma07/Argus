"""LLM wrapper: structured (pydantic) calls with token accounting, provider-switchable.

LLM_PROVIDER=anthropic (default) or gemini, set in .env. Every call site uses `parse()`
and gets back a validated pydantic object, so the rest of the agent is provider-agnostic.

Anthropic: pins the public API base URL (overridable via LLM_BASE_URL) so an ambient
ANTHROPIC_BASE_URL from the host shell can't redirect agent traffic, and uses server-side
refusal fallbacks ("default" routing).
Gemini: JSON-mode generation constrained by the same pydantic schema (response_json_schema).
"""

import os
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

import config.settings  # noqa: F401  (loads .env)

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
T = TypeVar("T", bound=BaseModel)


class Usage:
    def __init__(self):
        self.tokens = 0

    def add(self, n: int) -> None:
        self.tokens += int(n or 0)


def model_name() -> str:
    return GEMINI_MODEL if PROVIDER == "gemini" else MODEL


# ---------------------------------------------------------------- Anthropic

@lru_cache
def _anthropic():
    import anthropic
    return anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.getenv("LLM_BASE_URL", "https://api.anthropic.com"),
    )


def _parse_anthropic(system: str, user: str, schema: type[T], usage: Usage, effort: str, max_tokens: int) -> T:
    resp = _anthropic().beta.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    u = resp.usage
    usage.add((u.input_tokens or 0) + (u.output_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
              + (getattr(u, "cache_creation_input_tokens", 0) or 0))
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"LLM refused: {getattr(resp.stop_details, 'category', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("LLM output truncated (max_tokens)")
    return resp.parsed_output


# ---------------------------------------------------------------- Gemini

@lru_cache
def _gemini():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


# Map our effort levels onto Gemini thinking budgets (tokens of internal reasoning).
_THINKING = {"low": 1024, "medium": 4096, "high": 12288}


def _parse_gemini(system: str, user: str, schema: type[T], usage: Usage, effort: str, max_tokens: int) -> T:
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        max_output_tokens=max_tokens + _THINKING.get(effort, 4096),
        thinking_config=types.ThinkingConfig(thinking_budget=_THINKING.get(effort, 4096)),
        temperature=0.2,
    )
    resp = _gemini().models.generate_content(model=GEMINI_MODEL, contents=user, config=config)
    usage.add(getattr(resp.usage_metadata, "total_token_count", 0) if resp.usage_metadata else 0)
    if not resp.text:
        reason = resp.candidates[0].finish_reason if resp.candidates else "no candidates"
        raise RuntimeError(f"Gemini returned no content ({reason})")
    return schema.model_validate_json(resp.text)


def parse(system: str, user: str, schema: type[T], usage: Usage, effort: str = "high",
          max_tokens: int = 16000) -> T:
    if PROVIDER == "gemini":
        return _parse_gemini(system, user, schema, usage, effort, max_tokens)
    return _parse_anthropic(system, user, schema, usage, effort, max_tokens)
