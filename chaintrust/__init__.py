"""
chaintrust/__init__.py
Top-level package.  Configures structured logging at import time so every
sub-module inherits the same handler and formatter.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from chaintrust.config import get_config

__version__ = "0.1.0"


def _configure_logging() -> None:
    """Set up root logger with a human-readable structured format."""
    cfg = get_config()
    level_name: str = cfg.get("project", {}).get("log_level", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    # Also write to logs/chaintrust.log
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "chaintrust.log", encoding="utf-8")
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
        root.addHandler(file_handler)


_configure_logging()
