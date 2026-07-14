"""Test configuration: force a headless matplotlib backend before any import."""

import os

os.environ.setdefault("MPLBACKEND", "Agg")
