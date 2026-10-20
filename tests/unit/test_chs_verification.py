"""
tests/unit/test_chs_verification.py
Unit tests and cryptographic tamper tests for Level A CHS verification.
Verifies that:
1. An untampered CHS audit bundle passes all Level A checks completely offline.
2. Altered quality score in an interaction record is caught.
3. Deleted record in an audit bundle is caught.
4. Modified task difficulty weight in the difficulty table is caught.
5. Modified CHS parameter is caught via params_hash mismatch.
6. Altered claimed score is caught via recomputation and score hash mismatch.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from chaintrust.anchoring.bundle import create_chs_audit_bundle, load_bundle
from chaintrust.reputation.chs import CHSParams
from chaintrust.verifier.verifier import StandaloneVerifier, verify_chs_bundle


class DummyInteraction:
    def __init__(
        self,
        id_: int,
        agent_id: str,
        task_id: str,
        quality_score: float,
        timestamp: datetime,
        difficulty_weight: float = 0.5,
    ) -> None:
        self.id = id_
        self.agent_id = agent_id
        self.task_id = task_id
        self.quality_score = quality_score
        self.difficulty_weight = difficulty_weight
        self.passed = quality_score >= 0.7
        self.attempt = 1
        self.tests_passed = 8 if self.passed else 4
        self.tests_total = 10
        self.raw_output_hash = f"0x{'aa' * 32}"
        self.timestamp = timestamp
        self.epoch = 1


@pytest.fixture
def chs_bundle_setup(tmp_path: Path):
    """Generates a clean, valid CHS audit bundle with 4 interactions across 3 tasks."""
    agent_id = "agent_verified_01"
    epoch = 1
    t0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    inters = [
        DummyInteraction(1, agent_id, "task_easy", 0.95, t0, 0.40),
        DummyInteraction(2, agent_id, "task_med", 0.85, t0, 0.65),
        DummyInteraction(3, agent_id, "task_hard", 0.70, t0, 0.90),
        DummyInteraction(4, agent_id, "task_easy", 0.90, t0, 0.40),
    ]

    diff_table = {
        "task_easy": 0.40,
        "task_med": 0.65,
        "task_hard": 0.90,
    }

    params = CHSParams(
        decay_lambda=0.05,
        alpha0=2.0,
        d_min=0.2,
        m=5.0,
        beta=0.4,
        S_cap=1000.0,
    )

    bundle, bundle_path = create_chs_audit_bundle(
        agent_id=agent_id,
        epoch=epoch,
        interactions=inters,
        difficulty_table=diff_table,
        params=params,
        as_of=t0,
        output_dir=str(tmp_path),
    )

    return bundle, bundle_path, tmp_path


def test_untampered_bundle_verifies_successfully(chs_bundle_setup):
    """An untampered CHS bundle must pass all Level A verification checks."""
    bundle, bundle_path, _ = chs_bundle_setup

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(bundle_path)

    assert res.valid is True
    assert res.level_a_valid is True
    assert res.leaves_valid is True
    assert res.merkle_root_valid is True
    assert res.proofs_valid is True
    assert res.difficulty_root_valid is True
    assert res.params_hash_valid is True
    assert res.score_recomputed_valid is True
    assert res.score_hash_valid is True
    assert len(res.errors) == 0
    assert abs(res.recomputed_score - bundle["metadata"]["score"]) < 1e-4

    # Also test convenience function
    res_direct = verify_chs_bundle(bundle)
    assert res_direct.valid is True
    assert res_direct.level_a_valid is True


def test_tamper_altered_quality_score(chs_bundle_setup):
    """Tamper Test 1: Modifying quality score in an interaction record causes verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Agent inflates a score from 0.70 to 1.00
    tampered["records"][2]["quality_score"] = 1.0

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.leaves_valid is False
    assert len(res.errors) > 0
    assert any("Leaf hash mismatch" in err or "recomputation" in err for err in res.errors)


def test_tamper_deleted_record(chs_bundle_setup):
    """Tamper Test 2: Deleting a record from the audit bundle causes verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Attacker drops an interaction
    tampered["records"].pop(0)

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.leaves_valid is False
    assert len(res.errors) > 0


def test_tamper_modified_difficulty_weight(chs_bundle_setup):
    """Tamper Test 3: Modifying a task difficulty weight in difficulty table causes verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Attacker inflates the difficulty of 'task_easy' from 0.40 to 0.95
    for item in tampered["difficulty_table"]:
        if item["task_id"] == "task_easy":
            item["difficulty"] = 0.95

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.difficulty_root_valid is False
    assert any("Difficulty" in err for err in res.errors)


def test_tamper_modified_parameter(chs_bundle_setup):
    """Tamper Test 4: Modifying a parameter in the bundle causes params_hash verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Attacker changes saturation constant m from 5.0 to 1.0 to claim higher confidence
    tampered["parameters"]["m"] = 1.0

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.params_hash_valid is False
    assert any("Parameters hash mismatch" in err for err in res.errors)


def test_tamper_altered_claimed_score(chs_bundle_setup):
    """Tamper Test 5: Modifying the claimed score in metadata causes verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Attacker manually alters metadata score to 0.999
    tampered["metadata"]["score"] = 0.999000

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.score_recomputed_valid is False
    assert res.score_hash_valid is False
    assert any("Score recomputation mismatch" in err for err in res.errors)
    assert any("Score hash mismatch" in err for err in res.errors)


def test_tamper_altered_claimed_score_hash(chs_bundle_setup):
    """Tamper Test 6: Falsified score hash causes verification failure."""
    bundle, bundle_path, _ = chs_bundle_setup
    tampered = copy.deepcopy(bundle)

    # Attacker tampers score_hash directly
    tampered["metadata"]["score_hash"] = "0x" + "00" * 32

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.score_hash_valid is False
    assert any("Score hash mismatch" in err for err in res.errors)
