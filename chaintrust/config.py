"""
chaintrust/config.py
Configuration loader.

Merges config/config.yaml with environment variables from .env.
All other modules call `get_config()` — never read env vars directly.

Priority (highest to lowest):
  1. Actual environment variables (set in shell or CI)
  2. .env file (loaded by python-dotenv)
  3. config/config.yaml
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Locate project root = the directory containing this package
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_CONFIG_PATH  = _PROJECT_ROOT / "config" / "config.yaml"
_ENV_PATH     = _PROJECT_ROOT / ".env"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """
    Return the merged configuration dictionary (cached after first call).

    Env vars can override specific config values via the DATABASE_URL and
    LOG_LEVEL conventions defined in .env.example.
    """
    # 1. Load .env (silently skip if missing — CI sets vars directly)
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=False)
        logger.debug("Loaded .env from %s", _ENV_PATH)
    else:
        load_dotenv(override=False)

    # 2. Load YAML
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {_CONFIG_PATH}")
    cfg = _load_yaml(_CONFIG_PATH)

    # 3. Apply env-var overrides
    if db_url := os.getenv("DATABASE_URL"):
        cfg.setdefault("database", {})["url"] = db_url

    if log_level := os.getenv("LOG_LEVEL"):
        cfg.setdefault("project", {})["log_level"] = log_level

    return cfg


@lru_cache(maxsize=1)
def get_agents_config() -> list[dict[str, Any]]:
    """
    Return the list of agent definitions from config/agents.yaml.

    Only agents with ``enabled: true`` (default) are returned.
    """
    agents_path = _PROJECT_ROOT / "config" / "agents.yaml"
    if not agents_path.exists():
        raise FileNotFoundError(f"Agents config not found: {agents_path}")

    raw = _load_yaml(agents_path)
    agents: list[dict[str, Any]] = raw.get("agents", [])
    return [a for a in agents if a.get("enabled", True)]


def get_env(key: str, default: str | None = None) -> str | None:
    """
    Retrieve a secret from environment variables.

    Raises RuntimeError if the key is absent AND no default is given,
    so missing keys fail loudly rather than silently using empty strings.
    """
    get_config()
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file (see .env.example)."
        )
    return value


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return _PROJECT_ROOT
