"""Thin wrapper around the Claude API: one place for the model, credentials, caching and refusals.

Responses are cached on disk keyed by a hash of the full request, so re-running the eval does not
re-bill identical calls and results stay reproducible. Delete data/interim/llm_cache to force
fresh calls.
"""

from __future__ import annotations

import hashlib
import json
import os

import anthropic

from lore.paths import DATA_DIR, ROOT

MODEL = "claude-opus-5"
CACHE_DIR = DATA_DIR / "interim" / "llm_cache"
# Server-side fallback: if a safety classifier declines, the API re-runs the request on
# Anthropic's recommended fallback model instead of returning a refusal.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class RefusalError(RuntimeError):
    pass


def _load_dotenv() -> None:
    """Read KEY=value lines from the repo's .env without overriding the real environment."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _load_dotenv()
        _client = anthropic.Anthropic()
    return _client


def json_call(system: str, user: str, schema: dict, *, max_tokens: int = 16000) -> dict:
    """One request whose reply is JSON matching ``schema``; cached by request content."""
    request = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:24]
    cache = CACHE_DIR / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["output"]

    response = client().beta.messages.create(**request, betas=[FALLBACK_BETA], fallbacks="default")
    if response.stop_reason == "refusal":
        raise RefusalError(str(response.stop_details))
    if response.stop_reason == "max_tokens":
        raise RuntimeError("response hit max_tokens before the JSON was complete")
    text = next(b.text for b in response.content if b.type == "text")
    output = json.loads(text)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "model": response.model,
        "request_id": response._request_id,
        "usage": response.usage.to_dict(),
        "output": output,
    }
    cache.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return output
