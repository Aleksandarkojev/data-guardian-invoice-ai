"""One small place that talks to a model provider. Swap provider with LLM_PROVIDER in .env.

Every client has the same method:  complete(system, user) -> str
"""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv


class OpenAIClient:
    """Works with OpenAI, and with local models through an OpenAI-compatible server (for example Ollama)."""

    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        self.model = model or os.environ["OPENAI_MODEL"]
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY") or "not-needed-for-local",
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )

    def complete(self, system: str, user: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""


class AnthropicClient:
    def __init__(self, model: Optional[str] = None):
        import anthropic

        self.model = model or os.environ["ANTHROPIC_MODEL"]
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    def complete(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


class FakeClient:
    """For tests: returns prepared answers in order. No internet, no cost."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses:
            raise RuntimeError("FakeClient has no more prepared responses")
        return self.responses.pop(0)


def get_client(provider: Optional[str] = None):
    load_dotenv()
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    if provider == "openai":
        return OpenAIClient()
    if provider == "anthropic":
        return AnthropicClient()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r} (use 'openai' or 'anthropic')")
