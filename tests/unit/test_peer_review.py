"""
tests/unit/test_peer_review.py
Unit tests and Level B cryptographic verification tests for Phase 4:
- Peer review prompt construction and anonymity
- Response parsing (ratings and justifications)
- PeerRating database persistence
- Ratings graph Merkleization and inclusion proofs
- Level B bundle creation and offline verification
- Tamper tests on peer ratings graph
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from chaintrust.anchoring.bundle import create_chs_audit_bundle
from chaintrust.anchoring.merkle import (
    build_ratings_tree,
    compute_rating_leaf,
    verify_rating_leaf,
)
from chaintrust.db.models import Agent, PeerRating, Task, TaskSource
from chaintrust.db.session import get_session
from chaintrust.reputation.chs import CHSParams
from chaintrust.runner.peer_review import (
    format_peer_review_prompt,
    parse_peer_review_response,
)
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


def test_peer_review_prompt_formatting_and_anonymity():
    """Verify that peer-review prompts never leak the author's identity or model metadata."""
    prompt = format_peer_review_prompt(
        task_prompt="def add(a, b): return a + b",
        candidate_code="def add(a, b):\n    return a + b\n",
        test_status="Passed all 5 unit tests",
    )

    assert "Candidate Solution:" in prompt
    assert "def add(a, b):" in prompt
    assert "Passed all 5 unit tests" in prompt
    assert "RATING: <float between 0.0 and 1.0>" in prompt
    assert "JUSTIFICATION:" in prompt

    # Ensure no agent names, IDs or model identifiers are mentioned
    assert "agent_" not in prompt.lower()
    assert "gemini" not in prompt.lower()
    assert "groq" not in prompt.lower()


def test_peer_review_response_parsing():
    """Verify accurate extraction of numerical rating and text justification."""
    # Standard output
    resp1 = (
        "The solution is clean, robust, and correctly handles boundary conditions.\n\n"
        "RATING: 0.92\n"
        "JUSTIFICATION: Well-structured solution with optimal time complexity."
    )
    r1, j1 = parse_peer_review_response(resp1)
    assert r1 == 0.92
    assert "optimal time complexity" in j1

    # Clamping out-of-range ratings
    resp2 = "RATING: 1.5\nJUSTIFICATION: Too generous."
    r2, j2 = parse_peer_review_response(resp2)
    assert r2 == 1.0

    # Fallback when model uses natural language score
    resp3 = "I give this code a rating of 0.75 because it lacks comments."
    r3, j3 = parse_peer_review_response(resp3)
    assert r3 == 0.75


def test_peer_ratings_db_model():
    """Verify storing PeerRating records into the SQLite database."""
    with get_session() as session:
        # Create test agents and task if not exist
        ag1 = session.query(Agent).filter_by(agent_id="test_rater_1").first()
        if not ag1:
            ag1 = Agent(
                agent_id="test_rater_1",
                name="Rater Agent 1",
                provider="groq",
                model="llama3-70b",
                config_json="{}",
                config_hash="0x" + "11" * 32,
                stake=500,
            )
            session.add(ag1)

        ag2 = session.query(Agent).filter_by(agent_id="test_ratee_2").first()
        if not ag2:
            ag2 = Agent(
                agent_id="test_ratee_2",
                name="Ratee Agent 2",
                provider="gemini",
                model="gemini-1.5-pro",
                config_json="{}",
                config_hash="0x" + "22" * 32,
                stake=250,
            )
            session.add(ag2)

        tk = session.query(Task).filter_by(task_id="humaneval/test_pr_0").first()
        if not tk:
            tk = Task(
                task_id="humaneval/test_pr_0",
                source=TaskSource.HUMANEVAL,
                prompt="def foo(): pass",
                tests="assert True",
            )
            session.add(tk)

        session.commit()

        # Insert PeerRating
        pr = PeerRating(
            rater_id="test_rater_1",
            ratee_id="test_ratee_2",
            task_id="humaneval/test_pr_0",
            rating=0.88,
            justification="Passed all tests cleanly.",
            raw_output_hash="0x" + "33" * 32,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(pr)
        session.commit()

        # Query back
        found = session.query(PeerRating).filter_by(rater_id="test_rater_1", ratee_id="test_ratee_2").first()
        assert found is not None
        assert found.rating == 0.88
        assert found.justification == "Passed all tests cleanly."

        # Cleanup test records
        session.query(PeerRating).filter_by(rater_id="test_rater_1", ratee_id="test_ratee_2").delete()
        session.query(Task).filter_by(task_id="humaneval/test_pr_0").delete()
        session.query(Agent).filter(Agent.agent_id.in_(["test_rater_1", "test_ratee_2"])).delete()
        session.commit()


def test_ratings_merkle_tree_and_proofs():
    """Verify Merkle tree construction and inclusion proofs over peer rating records."""
    t0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    ratings = [
        {"rater_id": "agent_a", "ratee_id": "agent_b", "task_id": "task_1", "rating": 0.80, "justification": "Good", "raw_output_hash": "0x11", "timestamp": t0},
        {"rater_id": "agent_b", "ratee_id": "agent_a", "task_id": "task_1", "rating": 0.85, "justification": "Great", "raw_output_hash": "0x22", "timestamp": t0},
        {"rater_id": "agent_c", "ratee_id": "agent_a", "task_id": "task_2", "rating": 0.90, "justification": "Solid", "raw_output_hash": "0x33", "timestamp": t0},
    ]

    tree, root, records_with_proofs = build_ratings_tree(ratings)

    assert root.startswith("0x")
    assert len(records_with_proofs) == 3

    for item in records_with_proofs:
        proof = item["proof"]
        assert len(proof) > 0
        assert verify_rating_leaf(item, proof, root) is True


@pytest.fixture
def level_b_setup(tmp_path: Path):
    """Fixture providing a 3-agent setup with interaction logs and mutual peer ratings."""
    t0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    agents = [
        {"agent_id": "agent_1", "stake": 500, "family": ["gemini", "pro"]},
        {"agent_id": "agent_2", "stake": 300, "family": ["groq", "llama3"]},
        {"agent_id": "agent_3", "stake": 100, "family": ["openrouter", "claude"]},
    ]

    diff_table = {
        "task_1": 0.50,
        "task_2": 0.70,
    }

    inters = [
        DummyInteraction(1, "agent_1", "task_1", 0.90, t0, 0.50),
        DummyInteraction(2, "agent_1", "task_2", 0.80, t0, 0.70),
        DummyInteraction(3, "agent_2", "task_1", 0.85, t0, 0.50),
        DummyInteraction(4, "agent_2", "task_2", 0.75, t0, 0.70),
        DummyInteraction(5, "agent_3", "task_1", 0.60, t0, 0.50),
        DummyInteraction(6, "agent_3", "task_2", 0.65, t0, 0.70),
    ]

    ratings = [
        {"rater_id": "agent_1", "ratee_id": "agent_2", "task_id": "task_1", "rating": 0.85, "justification": "Good work", "raw_output_hash": "0x11", "timestamp": t0},
        {"rater_id": "agent_2", "ratee_id": "agent_1", "task_id": "task_1", "rating": 0.90, "justification": "Excellent", "raw_output_hash": "0x22", "timestamp": t0},
        {"rater_id": "agent_3", "ratee_id": "agent_1", "task_id": "task_2", "rating": 0.88, "justification": "Robust", "raw_output_hash": "0x33", "timestamp": t0},
        {"rater_id": "agent_1", "ratee_id": "agent_3", "task_id": "task_2", "rating": 0.70, "justification": "Adequate", "raw_output_hash": "0x44", "timestamp": t0},
    ]

    params = CHSParams(
        decay_lambda=0.05,
        alpha0=2.0,
        d_min=0.1,
        m=5.0,
        beta=0.85,
        S_cap=1000.0,
        w=0.3,
        omega=0.5,
        kappa1=0.5,
        kappa2=0.3,
        pi_max=0.8,
        N_iter=20,
    )

    agent_1_inters = [i for i in inters if i.agent_id == "agent_1"]

    bundle, bundle_path = create_chs_audit_bundle(
        agent_id="agent_1",
        epoch=1,
        interactions=agent_1_inters,
        difficulty_table=diff_table,
        params=params,
        ratings=ratings,
        agents=agents,
        as_of=t0,
        output_dir=str(tmp_path),
    )

    return bundle, bundle_path, tmp_path


def test_level_b_untouched_bundle_verification(level_b_setup):
    """An untouched Level B bundle must pass all Level A and Level B checks."""
    bundle, bundle_path, _ = level_b_setup

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(bundle_path)

    assert res.valid is True
    assert res.level_a_valid is True
    assert res.level_b_valid is True
    assert res.ratings_root_valid is True
    assert res.difficulty_root_valid is True
    assert res.merkle_root_valid is True
    assert res.leaves_valid is True
    assert res.proofs_valid is True
    assert res.params_hash_valid is True
    assert res.score_recomputed_valid is True
    assert res.score_hash_valid is True
    assert len(res.errors) == 0

    # Check convenience function
    res_direct = verify_chs_bundle(bundle)
    assert res_direct.valid is True
    assert res_direct.level_b_valid is True


def test_level_b_tamper_rating_value(level_b_setup):
    """Tamper Test: Modifying a rating in ratings_table triggers ratings_root failure."""
    bundle, _, _ = level_b_setup
    tampered = copy.deepcopy(bundle)

    # Attacker alters rating given by agent_3 to agent_1 from 0.88 to 1.00
    for r in tampered["ratings_table"]:
        if r["rater_id"] == "agent_3":
            r["rating"] = 1.00

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.ratings_root_valid is False
    assert any("Rating" in err or "Ratings" in err for err in res.errors)


def test_level_b_tamper_rater_identity(level_b_setup):
    """Tamper Test: Falsifying a rater identity in ratings_table triggers verification failure."""
    bundle, _, _ = level_b_setup
    tampered = copy.deepcopy(bundle)

    # Attacker changes rater from agent_3 to agent_1
    tampered["ratings_table"][2]["rater_id"] = "agent_1"

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.ratings_root_valid is False


def test_level_b_tamper_claimed_score(level_b_setup):
    """Tamper Test: Falsifying claimed score in Level B metadata triggers score recomputation mismatch."""
    bundle, _, _ = level_b_setup
    tampered = copy.deepcopy(bundle)

    # Attacker artificially boosts final composite score
    tampered["metadata"]["score"] = 0.999000

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(tampered)

    assert res.valid is False
    assert res.score_recomputed_valid is False
    assert res.score_hash_valid is False
    assert any("Level B score recomputation mismatch" in err for err in res.errors)
