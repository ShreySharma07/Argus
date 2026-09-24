"""LLM wrapper: structured (pydantic) calls with token accounting, provider-switchable.

LLM_PROVIDER=anthropic (default) or gemini, set in .env. Every call site uses `parse()`
and gets back a validated pydantic object, so the rest of the agent is provider-agnostic.

Anthropic: pins the public API base URL (overridable via LLM_BASE_URL) so an ambient
ANTHROPIC_BASE_URL from the host shell can't redirect agent traffic, and uses server-side
refusal fallbacks ("default" routing).
Gemini: JSON-mode generation constrained by the same pydantic schema (response_json_schema).
"""

import os
import re
import threading
import time
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

import config.settings  # noqa: F401  (loads .env)

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
# Tried in order when the current model is overloaded (503) or out of quota (429) after retries.
GEMINI_FALLBACKS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.8-flash,gemini-3.5-flash,gemini-flash-latest").split(",")
                    if m.strip()]
FALLBACK_BETA = "server-side-fallback-2026-07-01"
T = TypeVar("T", bound=BaseModel)


class Usage:
    def __init__(self):
        self.tokens = 0
        self.models: set[str] = set()

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
    usage.models.add(MODEL)
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


# Map our effort levels onto Gemini thinking (budget for 2.x models, level for 3.x models).
_THINKING = {"low": 1024, "medium": 4096, "high": 12288}
_LEVEL = {"low": "low", "medium": "medium", "high": "high"}

# Free-tier friendly pacing: at most GEMINI_RPM requests per minute across the whole process,
# and retry 429/503 with the server's suggested delay (or exponential backoff).
GEMINI_RPM = float(os.getenv("GEMINI_RPM", "5"))
_pace_lock = threading.Lock()
_last_call = [0.0]


def _pace() -> None:
    gap = 60.0 / max(GEMINI_RPM, 0.1)
    with _pace_lock:
        wait = _last_call[0] + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def _retry_delay(err: Exception, attempt: int) -> float:
    m = re.search(r"retry(?:Delay)?['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", str(err), re.I)
    return float(m.group(1)) + 2 if m else min(15 * 2 ** attempt, 180)


def _gemini_config(model: str, system: str, schema, effort: str, max_tokens: int):
    from google.genai import types
    gen3 = model.startswith("gemini-") and model.split("-")[1][:1] >= "3"
    thinking = (types.ThinkingConfig(thinking_level=_LEVEL.get(effort, "medium")) if gen3
                else types.ThinkingConfig(thinking_budget=_THINKING.get(effort, 4096)))
    return types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema.model_json_schema(),
        max_output_tokens=max_tokens + _THINKING.get(effort, 4096),
        thinking_config=thinking,
        temperature=0.2,
    )


GEMINI_CYCLES = int(os.getenv("GEMINI_CYCLES", "8"))  # rounds over the model list before giving up


def _parse_gemini(system: str, user: str, schema: type[T], usage: Usage, effort: str, max_tokens: int) -> T:
    """Round-robin over the configured models: free-tier capacity flickers per model, so on a
    503/429/500 we move to the next model rather than hammering one; 404 drops a model for good."""
    from google.genai import errors
    models = list(dict.fromkeys([GEMINI_MODEL] + GEMINI_FALLBACKS))
    last: Exception | None = None
    for cycle in range(GEMINI_CYCLES):
        for model in list(models):
            _pace()
            try:
                resp = _gemini().models.generate_content(
                    model=model, contents=user, config=_gemini_config(model, system, schema, effort, max_tokens))
            except errors.APIError as e:
                last = e
                if e.code == 404:  # retired / not offered to this key
                    models.remove(model)
                    continue
                if e.code not in (429, 500, 503):
                    raise
                continue
            usage.add(getattr(resp.usage_metadata, "total_token_count", 0) if resp.usage_metadata else 0)
            usage.models.add(model)
            if not resp.text:
                reason = resp.candidates[0].finish_reason if resp.candidates else "no candidates"
                raise RuntimeError(f"Gemini returned no content ({reason})")
            return schema.model_validate_json(resp.text)
        if not models:
            break
        wait = _retry_delay(last, 0) if last is not None and getattr(last, "code", None) == 429 else 20
        print(f"  [gemini] all models busy (cycle {cycle + 1}/{GEMINI_CYCLES}); waiting {wait:.0f}s", flush=True)
        time.sleep(wait)
    raise RuntimeError(f"all Gemini models unavailable: {last}")


def parse(system: str, user: str, schema: type[T], usage: Usage, effort: str = "high",
          max_tokens: int = 16000) -> T:
    if PROVIDER == "gemini":
        return _parse_gemini(system, user, schema, usage, effort, max_tokens)
    return _parse_anthropic(system, user, schema, usage, effort, max_tokens)
