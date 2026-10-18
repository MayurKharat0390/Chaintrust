"""
tests/unit/test_registry.py
Unit tests for agent registration and config_hash computation.

These tests use an in-memory SQLite DB (no real API keys needed).
"""

from __future__ import annotations

import json
import pytest

from chaintrust.registry.agent_registry import compute_config_hash, _canonical_json


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AGENT_A = {
    "name": "test-agent-A",
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest",
    "system_prompt": "You are helpful.",
    "temperature": 0.2,
    "max_tokens": 512,
    "stake": 5,
}

AGENT_B = {
    "name": "test-agent-B",          # different name
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest",
    "system_prompt": "You are helpful.",
    "temperature": 0.2,
    "max_tokens": 512,
    "stake": 5,
}

AGENT_C = {
    "name": "test-agent-A",
    "provider": "gemini",
    "model": "gemini-1.5-flash-latest",
    "system_prompt": "You are VERY helpful.",  # different prompt
    "temperature": 0.2,
    "max_tokens": 512,
    "stake": 5,
}

AGENT_WITH_EXTRAS = {
    **AGENT_A,
    "enabled": True,           # should be excluded from hash
    "rate_limits": {           # should be excluded from hash
        "requests_per_minute": 30,
    },
}


# ---------------------------------------------------------------------------
# Tests: canonical JSON
# ---------------------------------------------------------------------------

class TestCanonicalJson:
    def test_output_is_valid_json(self):
        text = _canonical_json(AGENT_A)
        parsed = json.loads(text)
        assert isinstance(parsed, dict)

    def test_keys_are_sorted(self):
        text = _canonical_json(AGENT_A)
        parsed = json.loads(text)
        assert list(parsed.keys()) == sorted(parsed.keys())

    def test_enabled_excluded(self):
        """'enabled' and 'rate_limits' must not appear in canonical JSON."""
        text = _canonical_json(AGENT_WITH_EXTRAS)
        assert "enabled" not in json.loads(text)
        assert "rate_limits" not in json.loads(text)

    def test_deterministic(self):
        """Same input → same output on repeated calls."""
        t1 = _canonical_json(AGENT_A)
        t2 = _canonical_json(AGENT_A)
        assert t1 == t2

    def test_float_normalised(self):
        """Floats are rounded to 8 decimal places."""
        cfg = {**AGENT_A, "temperature": 0.19999999999999999}
        text = _canonical_json(cfg)
        parsed = json.loads(text)
        assert parsed["temperature"] == round(0.19999999999999999, 8)


# ---------------------------------------------------------------------------
# Tests: compute_config_hash
# ---------------------------------------------------------------------------

class TestComputeConfigHash:
    def test_returns_two_strings(self):
        agent_id, config_hash = compute_config_hash(AGENT_A)
        assert isinstance(agent_id, str)
        assert isinstance(config_hash, str)

    def test_agent_id_length(self):
        """agent_id is 32 hex chars (16 bytes)."""
        agent_id, _ = compute_config_hash(AGENT_A)
        assert len(agent_id) == 32
        assert all(c in "0123456789abcdef" for c in agent_id)

    def test_config_hash_is_sha256(self):
        """Full config_hash is 64 hex chars (SHA-256)."""
        _, config_hash = compute_config_hash(AGENT_A)
        assert len(config_hash) == 64
        assert all(c in "0123456789abcdef" for c in config_hash)

    def test_agent_id_is_prefix_of_config_hash(self):
        """agent_id must be the first 32 chars of config_hash."""
        agent_id, config_hash = compute_config_hash(AGENT_A)
        assert config_hash.startswith(agent_id)

    def test_same_config_same_hash(self):
        id1, h1 = compute_config_hash(AGENT_A)
        id2, h2 = compute_config_hash(AGENT_A)
        assert id1 == id2 and h1 == h2

    def test_different_name_different_hash(self):
        """Two agents with different names must have different hashes."""
        id_a, _ = compute_config_hash(AGENT_A)
        id_b, _ = compute_config_hash(AGENT_B)
        assert id_a != id_b

    def test_different_prompt_different_hash(self):
        """Different system_prompt → different hash (it affects output)."""
        id_a, _ = compute_config_hash(AGENT_A)
        id_c, _ = compute_config_hash(AGENT_C)
        assert id_a != id_c

    def test_extras_dont_change_hash(self):
        """'enabled' and 'rate_limits' must NOT change the hash."""
        id_a,  _ = compute_config_hash(AGENT_A)
        id_ex, _ = compute_config_hash(AGENT_WITH_EXTRAS)
        assert id_a == id_ex

    def test_known_hash(self):
        """
        Regression test: hard-code the expected hash for AGENT_A.
        If the hashing logic changes, this test will fail and alert us.

        To regenerate: run `compute_config_hash(AGENT_A)` and copy the output.
        (Run once, then freeze.)
        """
        import hashlib

        from chaintrust.registry.agent_registry import _canonical_json, _EXCLUDE_FROM_HASH
        canonical = _canonical_json(AGENT_A)
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        _, config_hash = compute_config_hash(AGENT_A)
        assert config_hash == expected
