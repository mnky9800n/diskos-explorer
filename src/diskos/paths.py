"""Resolve the DISKOS data root.

This is the only module that knows where the data lives. Every parser takes an
explicit path argument; callers get the root from here. No ``os.chdir`` anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import Config, load_config


def diskos_root(config: Config | None = None) -> Path:
    """Return the resolved DISKOS data root as a Path.

    Resolution order:
      1. The ``DISKOS_ROOT`` environment variable, if set (handy for pointing at
         a sample tree without editing committed config).
      2. ``[paths].prefer`` in config: "diskos_root" (run on lambda-scalar) or
         "local_sample" (laptop dev against an rsync'd subset).
    Raises a clear error if the chosen root does not exist.
    """
    cfg = config or load_config()

    env_root = os.environ.get("DISKOS_ROOT")
    if env_root:
        raw = env_root
    elif cfg.prefer == "local_sample":
        raw = cfg.local_sample
    else:
        raw = cfg.diskos_root

    # Resolve relative paths (e.g. ./data/DISKOS) against the project root.
    root = Path(raw)
    if not root.is_absolute():
        root = (cfg.project_root / root).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"DISKOS root not found: {root}\n"
            f"(prefer = {cfg.prefer!r}). Either run on lambda-scalar with "
            f"prefer = 'diskos_root', or rsync a sample into {cfg.local_sample} "
            f"and set prefer = 'local_sample'. See README."
        )
    return root
