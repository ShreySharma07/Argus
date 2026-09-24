"""Claude wrapper: structured (pydantic) calls with token accounting.

Pins the public API base URL (overridable via LLM_BASE_URL) so an ambient
ANTHROPIC_BASE_URL from the host shell can't redirect agent traffic. Uses
server-side refusal fallbacks ("default" routing) so a safety decline is
retried on Anthropic's recommended fallback model instead of failing the case.
"""

import os
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

import config.settings  # noqa: F401  (loads .env)

MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
T = TypeVar("T", bound=BaseModel)


@lru_cache
def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.getenv("LLM_BASE_URL", "https://api.anthropic.com"),
    )


class Usage:
    def __init__(self):
        self.tokens = 0

    def add(self, usage) -> None:
        self.tokens += (usage.input_tokens or 0) + (usage.output_tokens or 0)
        self.tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0


def parse(system: str, user: str, schema: type[T], usage: Usage, effort: str = "high",
          max_tokens: int = 16000) -> T:
    resp = client().beta.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    usage.add(resp.usage)
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"LLM refused: {getattr(resp.stop_details, 'category', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("LLM output truncated (max_tokens)")
    return resp.parsed_output
