"""Load and resolve diskosAI configuration.

This is the only module that reads config.toml. Everything else takes a resolved
Config object or explicit arguments, so nothing hardcodes paths or secrets.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_CONFIG_NAME = "config.toml"


@dataclass(frozen=True)
class LLMProfile:
    """One model/compute endpoint. Selected by name; swappable via config only."""

    name: str
    base_url: str
    model: str
    api_key_env: str

    def api_key(self) -> str | None:
        """Resolve the API key from the environment (never stored in config)."""
        return os.environ.get(self.api_key_env)


@dataclass(frozen=True)
class Config:
    diskos_root: str
    local_sample: str
    prefer: str
    default_profile: str
    profiles: dict[str, LLMProfile] = field(default_factory=dict)
    project_root: Path = Path(".")
    taxon_decisions: str = "taxon_decisions.csv"
    npd_dir: str = "./data/npd"
    ocr_dir: str = "./data/ocr"

    def decisions_path(self) -> Path:
        """Absolute path to the persistent taxon same/different decisions file."""
        path = Path(self.taxon_decisions)
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def npd_path(self) -> Path:
        """Absolute path to the cached Sodir/NPD FactPages CSV directory."""
        path = Path(self.npd_dir)
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def ocr_path(self) -> Path:
        """Absolute path to the cached OCR-transcript directory."""
        path = Path(self.ocr_dir)
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def profile(self, name: str | None = None) -> LLMProfile:
        """Return a model profile by name, defaulting to ``default_profile``."""
        key = name or self.default_profile
        if key not in self.profiles:
            available = ", ".join(sorted(self.profiles)) or "(none)"
            raise KeyError(f"Unknown LLM profile {key!r}. Available: {available}")
        return self.profiles[key]


def find_config(start: Path | None = None) -> Path:
    """Walk up from ``start`` (or cwd) to find config.toml."""
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / DEFAULT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Could not find {DEFAULT_CONFIG_NAME} in {start} or any parent directory."
    )


def load_config(path: Path | None = None) -> Config:
    """Load config.toml (+ .env) into a typed Config.

    Args:
        path: Explicit config path. If omitted, search upward from cwd.
    """
    config_path = Path(path) if path else find_config()
    project_root = config_path.parent

    # Load secrets from a sibling .env if present; real env vars still win.
    load_dotenv(project_root / ".env")

    with open(config_path, "rb") as handle:
        raw = tomllib.load(handle)

    paths = raw.get("paths", {})
    llm = raw.get("llm", {})

    profiles: dict[str, LLMProfile] = {}
    for name, spec in llm.get("profiles", {}).items():
        profiles[name] = LLMProfile(
            name=name,
            base_url=spec.get("base_url", ""),
            model=spec.get("model", ""),
            api_key_env=spec.get("api_key_env", ""),
        )

    return Config(
        diskos_root=paths.get("diskos_root", ""),
        local_sample=paths.get("local_sample", "./data/DISKOS"),
        prefer=paths.get("prefer", "diskos_root"),
        default_profile=llm.get("default_profile", "jack-serve"),
        profiles=profiles,
        project_root=project_root,
        taxon_decisions=paths.get("taxon_decisions", "taxon_decisions.csv"),
        npd_dir=paths.get("npd_dir", "./data/npd"),
        ocr_dir=paths.get("ocr_dir", "./data/ocr"),
    )
