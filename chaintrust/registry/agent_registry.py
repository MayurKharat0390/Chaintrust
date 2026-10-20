"""
chaintrust/registry/agent_registry.py
Loads agents from agents.yaml, computes their config_hash, and upserts
them into the `agents` table.

config_hash computation
-----------------------
1. Take the agent dict (all keys from agents.yaml).
2. Remove ephemeral fields: 'enabled', 'rate_limits' (these don't affect output).
3. Serialize to canonical JSON: sorted keys, no extra whitespace, UTF-8.
4. SHA-256 hash the UTF-8 bytes → hex string.
5. Use the first 32 hex chars (16 bytes) as the agent_id (short enough to
   embed in Merkle leaves but still collision-resistant for our use case).
   The full 64-char hash is stored separately in config_hash for audit.

Why first-16-bytes as agent_id?
   We want agent_id to fit neatly in Ethereum bytes32 and be human-readable
   in logs.  A truncated hash is fine for a research prototype with < 1000 agents.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from chaintrust.config import get_agents_config
from chaintrust.db.session import get_session
from chaintrust.db.models import Agent

logger = logging.getLogger(__name__)

# Fields excluded from config_hash (runtime/infra concerns, not model behaviour)
_EXCLUDE_FROM_HASH = {"enabled", "rate_limits"}


def _canonical_json(config: dict[str, Any]) -> str:
    """
    Produce canonical JSON: sorted keys, UTF-8, no extra whitespace.
    Floats are rounded to 8 decimal places to avoid platform differences.
    """
    def _normalise(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 8)
        if isinstance(obj, dict):
            return {k: _normalise(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_normalise(v) for v in obj]
        return obj

    cleaned = {k: v for k, v in config.items() if k not in _EXCLUDE_FROM_HASH}
    return json.dumps(_normalise(cleaned), ensure_ascii=False, separators=(",", ":"))


def compute_config_hash(config: dict[str, Any]) -> tuple[str, str]:
    """
    Return ``(agent_id, config_hash)`` for an agent config dict.

    Parameters
    ----------
    config:
        Raw agent config dict from agents.yaml.

    Returns
    -------
    agent_id:
        First 32 hex chars of SHA-256 (16 bytes, deterministic).
    config_hash:
        Full 64 hex chars of SHA-256 for audit / tamper detection.
    """
    canonical = _canonical_json(config)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    agent_id    = digest[:32]
    config_hash = digest
    return agent_id, config_hash


class AgentRegistry:
    """
    Manages agent registration and lookup.

    Usage
    -----
        registry = AgentRegistry()
        agents = registry.register_all()   # upserts all enabled agents
        agent  = registry.get("gemini-flash-default")
    """

    def register_all(self) -> list[Agent]:
        """
        Load enabled agents from agents.yaml and upsert them into the DB.

        Returns a list of Agent ORM objects (as committed to the DB).
        Existing agents whose config hasn't changed are left untouched.
        If an agent's config changes (name kept, hash changed), a new row is
        inserted and a warning is logged — the old agent_id is preserved in the
        interactions table.
        """
        raw_agents = get_agents_config()
        registered: list[Agent] = []

        with get_session() as session:
            for raw in raw_agents:
                agent_id, config_hash = compute_config_hash(raw)
                canonical = _canonical_json(raw)

                agent_obj = Agent(
                    agent_id    = agent_id,
                    name        = raw["name"],
                    provider    = raw["provider"],
                    model       = raw["model"],
                    config_json = canonical,
                    config_hash = config_hash,
                    stake       = raw.get("stake", 0),
                )

                # Upsert: check if agent with agent_id or name already exists
                existing = (
                    session.query(Agent)
                    .filter((Agent.agent_id == agent_id) | (Agent.name == raw["name"]))
                    .first()
                )
                if existing:
                    logger.debug("Agent %s (%s) already registered, skipping insert.", raw["name"], existing.agent_id)
                    registered.append(existing)
                    continue

                stmt = (
                    sqlite_insert(Agent)
                    .values(
                        agent_id    = agent_obj.agent_id,
                        name        = agent_obj.name,
                        provider    = agent_obj.provider,
                        model       = agent_obj.model,
                        config_json = agent_obj.config_json,
                        config_hash = agent_obj.config_hash,
                        stake       = agent_obj.stake,
                    )
                    .on_conflict_do_nothing(index_elements=["agent_id"])
                )
                session.execute(stmt)
                logger.info(
                    "Registered agent: %s  id=%s  provider=%s  model=%s",
                    raw["name"], agent_id, raw["provider"], raw["model"],
                )
                registered.append(agent_obj)

        return registered

    def get_all(self) -> list[Agent]:
        """Return all Agent rows from the database."""
        with get_session() as session:
            return session.query(Agent).all()

    def get_by_name(self, name: str) -> Agent | None:
        """Return an Agent by its human-readable name, or None."""
        with get_session() as session:
            return session.query(Agent).filter(Agent.name == name).first()

    def get_by_id(self, agent_id: str) -> Agent | None:
        """Return an Agent by its agent_id, or None."""
        with get_session() as session:
            return session.query(Agent).get(agent_id)

    def register_agent(self, config: dict[str, Any]) -> Agent:
        """
        Register a single agent from a raw config dict.

        Useful for programmatic registration (e.g. Sybil experiment clones).

        Parameters
        ----------
        config:
            Dict with at minimum: name, provider, model, system_prompt,
            temperature, max_tokens.  stake defaults to 0.

        Returns
        -------
        Agent ORM object (attributes populated, not bound to a session).
        """
        agent_id, config_hash = compute_config_hash(config)
        canonical = _canonical_json(config)

        with get_session() as session:
            stmt = (
                sqlite_insert(Agent)
                .values(
                    agent_id    = agent_id,
                    name        = config["name"],
                    provider    = config["provider"],
                    model       = config["model"],
                    config_json = canonical,
                    config_hash = config_hash,
                    stake       = config.get("stake", 0),
                )
                .on_conflict_do_nothing(index_elements=["agent_id"])
            )
            session.execute(stmt)

        logger.info("Registered single agent: %s (id=%s)", config["name"], agent_id)
        return Agent(
            agent_id    = agent_id,
            name        = config["name"],
            provider    = config["provider"],
            model       = config["model"],
            config_json = canonical,
            config_hash = config_hash,
            stake       = config.get("stake", 0),
        )
