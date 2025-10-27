"\"\"\"Simple OpenAI client wrapper with retry and caching helpers.\"\"\""

from __future__ import annotations

import json
import os
import ssl
import time
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .utils import ParseError, short_hash


class LLMClient:
    """Minimal wrapper around OpenAI's chat completion endpoint with retries."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_retries: int = 5,
        retry_backoff: float = 2.0,
        timeout: int = 60,
        endpoint: str = "https://api.openai.com/v1/chat/completions",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable not set.")
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        self.endpoint = endpoint
        self.ssl_context = self._build_ssl_context()

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        context = ssl.create_default_context()
        # Prefer certifi's CA bundle if available (improves compatibility on macOS).
        try:
            import certifi  # type: ignore

            context.load_verify_locations(certifi.where())
        except Exception:
            # Fall back to the system trust store; optionally load the macOS bundle.
            candidate = Path("/etc/ssl/cert.pem")
            if candidate.exists():
                try:
                    context.load_verify_locations(str(candidate))
                except ssl.SSLError:
                    pass
        return context

    def _request_completion(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a careful analyst who strictly follows output formatting instructions.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")

        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTPError {status}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"URLError: {exc}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected API response format: {data}") from exc

    def generate(self, prompt: str) -> str:
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._request_completion(prompt)
            except RuntimeError as exc:
                message = str(exc)
                # Retry on rate limit or server error codes.
                if any(code in message for code in ("429", "500", "502", "503", "504")) and attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= self.retry_backoff
                    continue
                raise


def cache_path(base_dir: Path, film_id: str, stage_key: str, prompt: str, prompt_version: str) -> Path:
    digest = short_hash(prompt + stage_key + prompt_version)
    return base_dir / stage_key / f"{film_id}.raw.{digest}.txt"


def write_cache(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_cache(path: Path) -> Optional[str]:
    return path.read_text(encoding="utf-8") if path.exists() else None
