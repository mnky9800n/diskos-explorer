"""Thin OpenAI-compatible chat client.

Transport only, no task logic. One class that both batch jobs and the future web
backend construct identically from a named config profile, so switching between
lambda-scalar Ollama, Modal, or a cloud model is a config change, not code.

The ``openai`` SDK speaks any OpenAI-compatible endpoint (including Ollama). It is
imported lazily and can be dependency-injected, so this module imports and unit
tests without the SDK installed or any network access.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ..config import Config
from .profiles import system_prompt_for


class LLMClient:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, *, system: str = "", client=None):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.system = system
        self._client = client  # injectable; real one built lazily

    @classmethod
    def from_profile(cls, name: str | None, config: Config) -> "LLMClient":
        profile = config.profile(name)
        return cls(
            base_url=profile.base_url,
            model=profile.model,
            api_key=profile.api_key(),
            system=system_prompt_for(profile.name),
            client=None,
        )

    def _ensure(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key or "not-needed")
        return self._client

    def _with_system(self, messages: list[dict]) -> list[dict]:
        if self.system and not (messages and messages[0].get("role") == "system"):
            return [{"role": "system", "content": self.system}, *messages]
        return messages

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send chat messages, return the assistant text."""
        resp = self._ensure().chat.completions.create(
            model=self.model, messages=self._with_system(messages), **kwargs
        )
        return resp.choices[0].message.content

    def ask(self, prompt: str, **kwargs) -> str:
        """Convenience: a single user turn."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def chat_vision(self, prompt: str, image_paths: list[str | Path], **kwargs) -> str:
        """Send a prompt plus one or more local images (for microscope triage).

        Images are embedded as data URIs so no external host is contacted.
        """
        content: list[dict] = [{"type": "text", "text": prompt}]
        for image_path in image_paths:
            data = base64.b64encode(Path(image_path).read_bytes()).decode()
            suffix = Path(image_path).suffix.lstrip(".").lower() or "png"
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/{suffix};base64,{data}"}}
            )
        return self.chat([{"role": "user", "content": content}], **kwargs)
