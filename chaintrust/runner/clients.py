"""
chaintrust/runner/clients.py
One AgentClient per provider, all behind the same interface:

    client.generate(prompt: str) -> GenerateResult

Adding a new provider:
  1. Create a subclass of AgentClient.
  2. Implement _call(prompt) -> GenerateResult.
  3. Register it in PROVIDER_MAP at the bottom.

Rate limiting, retries, and logging are handled by the Runner; the client
is responsible only for the API call itself.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from chaintrust.config import get_env

logger = logging.getLogger(__name__)


@dataclass
class GenerateResult:
    """
    Result of one model generation call.

    Attributes
    ----------
    text:        Raw model output string.
    tokens_in:   Prompt token count (None if provider doesn't report it).
    tokens_out:  Completion token count (None if not reported).
    latency_ms:  Wall-clock time of the API call in milliseconds.
    model_used:  Actual model ID returned by the provider (may differ from requested).
    """
    text:       str
    tokens_in:  int | None = None
    tokens_out: int | None = None
    latency_ms: int = 0
    model_used: str | None = None


class AgentClient(ABC):
    """
    Abstract base for all provider clients.

    Subclasses implement `_call(prompt)` and set `provider` class attribute.
    """
    provider: str = "abstract"

    def __init__(self, agent_config: dict[str, Any]) -> None:
        self.config      = agent_config
        self.model       = agent_config["model"]
        self.temperature = float(agent_config.get("temperature", 0.2))
        self.max_tokens  = int(agent_config.get("max_tokens", 1024))
        self.system_prompt = agent_config.get("system_prompt", "")

    def generate(self, prompt: str) -> GenerateResult:
        """
        Call the model and return a GenerateResult.

        Raises any provider exceptions so the runner can handle retries.
        """
        t0 = time.monotonic()
        result = self._call(prompt)
        result.latency_ms = int((time.monotonic() - t0) * 1000)
        logger.debug(
            "[%s] tokens_in=%s tokens_out=%s latency=%dms",
            self.provider, result.tokens_in, result.tokens_out, result.latency_ms,
        )
        return result

    @abstractmethod
    def _call(self, prompt: str) -> GenerateResult:
        """Provider-specific API call. Returns GenerateResult (latency_ms may be 0)."""
        ...


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiClient(AgentClient):
    """Client for Google Gemini via the google-generativeai SDK."""
    provider = "gemini"

    def __init__(self, agent_config: dict[str, Any]) -> None:
        super().__init__(agent_config)
        import google.generativeai as genai  # type: ignore
        api_key = get_env("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_obj = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=self.system_prompt or None,
        )

    def _call(self, prompt: str) -> GenerateResult:
        response = self._model_obj.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        text = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        tokens_in  = getattr(usage, "prompt_token_count",     None)
        tokens_out = getattr(usage, "candidates_token_count", None)
        return GenerateResult(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_used=self.model,
        )


# ---------------------------------------------------------------------------
# Groq
# ---------------------------------------------------------------------------

class GroqClient(AgentClient):
    """Client for Groq via the official groq Python SDK."""
    provider = "groq"

    def __init__(self, agent_config: dict[str, Any]) -> None:
        super().__init__(agent_config)
        from groq import Groq  # type: ignore
        self._client = Groq(api_key=get_env("GROQ_API_KEY"))

    def _call(self, prompt: str) -> GenerateResult:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        return GenerateResult(
            text=text,
            tokens_in=usage.prompt_tokens if usage else None,
            tokens_out=usage.completion_tokens if usage else None,
            model_used=response.model,
        )


# ---------------------------------------------------------------------------
# OpenRouter
# ---------------------------------------------------------------------------

class OpenRouterClient(AgentClient):
    """
    Client for OpenRouter using the openai-compatible REST API.

    OpenRouter is OpenAI-API-compatible; we use the openai SDK with a
    custom base URL and an Authorization header.
    """
    provider = "openrouter"

    def __init__(self, agent_config: dict[str, Any]) -> None:
        super().__init__(agent_config)
        from openai import OpenAI  # type: ignore
        self._client = OpenAI(
            api_key=get_env("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/chaintrust",
                "X-Title": "ChainTrust Research",
            },
        )

    def _call(self, prompt: str) -> GenerateResult:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        return GenerateResult(
            text=text,
            tokens_in=usage.prompt_tokens if usage else None,
            tokens_out=usage.completion_tokens if usage else None,
            model_used=response.model,
        )


# ---------------------------------------------------------------------------
# Ollama (local)
# ---------------------------------------------------------------------------

class OllamaClient(AgentClient):
    """
    Client for Ollama local inference server.

    Uses the Ollama REST API directly (no SDK needed).
    Requires:  ollama serve  (and the model pulled with  ollama pull <model>).
    """
    provider = "ollama"

    def __init__(self, agent_config: dict[str, Any]) -> None:
        super().__init__(agent_config)
        import os
        import httpx  # type: ignore
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=120.0)

    def _call(self, prompt: str) -> GenerateResult:
        # Build the prompt with system prefix if provided
        full_prompt = prompt
        if self.system_prompt:
            full_prompt = f"{self.system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        resp = self._http.post(f"{self._base_url}/api/generate", json=payload)
        resp.raise_for_status()
        data = resp.json()

        text = data.get("response", "")
        return GenerateResult(
            text=text,
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
            model_used=data.get("model", self.model),
        )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

PROVIDER_MAP: dict[str, type[AgentClient]] = {
    "gemini":      GeminiClient,
    "groq":        GroqClient,
    "openrouter":  OpenRouterClient,
    "ollama":      OllamaClient,
}


def get_client(agent_config: dict[str, Any]) -> AgentClient:
    """
    Instantiate the correct AgentClient for the given agent config.

    Parameters
    ----------
    agent_config:
        Raw agent config dict (from agents.yaml or the DB).

    Raises
    ------
    ValueError if the provider is unknown.
    """
    provider = agent_config.get("provider", "").lower()
    cls = PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            f"Available: {list(PROVIDER_MAP.keys())}"
        )
    return cls(agent_config)
