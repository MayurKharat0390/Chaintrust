"""
tests/unit/test_chs.py
Unit tests for the ChainTrust Hybrid Score (CHS) algorithm.

Includes:
1. Small hand-computed fixture (5 agents, 4 tasks) with step-by-step arithmetic verification.
2. Step-by-step unit tests: difficulty, shrinkage, consistency, propagation, defense.
3. Determinism & order-invariance tests (shuffling agents, tasks, interactions, ratings).
4. Clone invariance test (adding K family clones does not change task difficulty).
5. Edge cases: zero interactions, task attempted by single family, all-zero ratings.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from chaintrust.reputation.chs import (
    CHSParams,
    CHSScorer,
    chs,
    compute_params_hash,
    defense,
    difficulty,
    direct_scores,
    load_chs_params,
    propagate,
)


# ---------------------------------------------------------------------------
# Hand-Computed Fixture Setup
# ---------------------------------------------------------------------------
# 5 agents:
#   a1: (gemini, flash), stake=100
#   a2: (gemini, flash), stake=50   [Same family as a1]
#   a3: (groq, llama3),  stake=200
#   a4: (openrouter, mistral), stake=50
#   a5: (ollama, qwen),  stake=0    [0 interactions]
#
# 4 tasks: t1, t2, t3, t4.
# Reference time as_of = 2026-10-20 12:00:00 UTC. All attempts at as_of (age = 0, delta = 1.0).
#
# Task t1:
#   a1 (F1): q = 1.0
#   a2 (F1): q = 1.0  => F1 mean = 1.0
#   a3 (F2): q = 0.8  => F2 mean = 0.8
#   F_t1 = 2 families. sum = 1.8.
#   p_t1 = (1.8 + 2.0*0.5)/(2 + 2) = 2.8 / 4 = 0.70
#   d_t1 = 1 - 0.70 = 0.30
#
# Task t2:
#   a3 (F2): q = 0.4  => F2 mean = 0.4
#   a4 (F3): q = 0.6  => F3 mean = 0.6
#   F_t2 = 2 families. sum = 1.0.
#   p_t2 = (1.0 + 1.0)/4 = 0.50
#   d_t2 = 1 - 0.50 = 0.50
#
# Task t3:
#   a1 (F1): q = 0.2  => F1 mean = 0.2
#   F_t3 = 1 family. sum = 0.2.
#   p_t3 = (0.2 + 1.0)/(1 + 2) = 1.2 / 3 = 0.40
#   d_t3 = 1 - 0.40 = 0.60
#
# Task t4:
#   a4 (F3): q = 0.0  => F3 mean = 0.0
#   F_t4 = 1 family. sum = 0.0.
#   p_t4 = (0.0 + 1.0)/(1 + 2) = 1.0 / 3 = 1/3
#   d_t4 = 1 - 1/3 = 2/3 (~0.666666667)
#
# Direct Evidence (n_a, D_a, D'_a):
#   a1: t1 (w=0.30, q=1.0), t3 (w=0.60, q=0.2)
#       n_a1 = 0.90, D_a1 = (0.30*1.0 + 0.60*0.2)/0.90 = 0.42/0.90 = 7/15 (~0.466666667)
#   a2: t1 (w=0.30, q=1.0)
#       n_a2 = 0.30, D_a2 = 1.0
#   a3: t1 (w=0.30, q=0.8), t2 (w=0.50, q=0.4)
#       n_a3 = 0.80, D_a3 = (0.24 + 0.20)/0.80 = 0.44/0.80 = 0.55
#   a4: t2 (w=0.50, q=0.6), t4 (w=2/3, q=0.0)
#       n_a4 = 0.50 + 2/3 = 7/6 (~1.166666667)
#       D_a4 = (0.50*0.6 + 0)/ (7/6) = 0.30 / (7/6) = 1.8/7 (~0.257142857)
#   a5: 0 interactions => n_a5 = 0.0, D_a5 = 0.0
#
#   mu0 = mean(D_a for a in [a1,a2,a3,a4])
#       = (7/15 + 1.0 + 0.55 + 1.8/7) / 4 = 2.273809524 / 4 = 0.568452381
#   Shrinkage with m = 5:
#   D'_a1 = (0.90 * (7/15) + 5 * mu0) / 5.90 = (0.42 + 2.842261905) / 5.90 = 0.552925747
#   D'_a2 = (0.30 * 1.0 + 5 * mu0) / 5.30    = (0.30 + 2.842261905) / 5.30 = 0.592879605
#   D'_a3 = (0.80 * 0.55 + 5 * mu0) / 5.80   = (0.44 + 2.842261905) / 5.80 = 0.565907225
#   D'_a4 = (7/6 * (1.8/7) + 5 * mu0) / (37/6) = (0.30 + 2.842261905) / (37/6) = 0.509555985
#   D'_a5 = (0 + 5 * mu0) / 5 = mu0 = 0.568452381
#
# Layer 1 CHS (no ratings => T~ = D', pi = 0, C = 1.0):
#   CHS_a = round(D'_a, 6)
#   a1: 0.552926
#   a2: 0.592880
#   a3: 0.565907
#   a4: 0.509556
#   a5: 0.568452
# ---------------------------------------------------------------------------

@pytest.fixture
def hand_computed_fixture():
    as_of = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    P = CHSParams(
        decay_lambda=math.log(2.0) / 30.0,
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
        N_iter=50,
    )

    agents = [
        {"agent_id": "a1", "provider": "gemini", "model": "flash", "stake": 100},
        {"agent_id": "a2", "provider": "gemini", "model": "flash", "stake": 50},
        {"agent_id": "a3", "provider": "groq", "model": "llama3", "stake": 200},
        {"agent_id": "a4", "provider": "openrouter", "model": "mistral", "stake": 50},
        {"agent_id": "a5", "provider": "ollama", "model": "qwen", "stake": 0},
    ]

    interactions = [
        # Task t1
        {"agent_id": "a1", "task_id": "t1", "quality_score": 1.0, "timestamp": as_of},
        {"agent_id": "a2", "task_id": "t1", "quality_score": 1.0, "timestamp": as_of},
        {"agent_id": "a3", "task_id": "t1", "quality_score": 0.8, "timestamp": as_of},
        # Task t2
        {"agent_id": "a3", "task_id": "t2", "quality_score": 0.4, "timestamp": as_of},
        {"agent_id": "a4", "task_id": "t2", "quality_score": 0.6, "timestamp": as_of},
        # Task t3
        {"agent_id": "a1", "task_id": "t3", "quality_score": 0.2, "timestamp": as_of},
        # Task t4
        {"agent_id": "a4", "task_id": "t4", "quality_score": 0.0, "timestamp": as_of},
    ]

    return {
        "as_of": as_of,
        "P": P,
        "agents": agents,
        "interactions": interactions,
        "expected_difficulty": {
            "t1": 0.30,
            "t2": 0.50,
            "t3": 0.60,
            "t4": round(2.0 / 3.0, 9),
        },
        "expected_D_prime": {
            "a1": 0.552925747,
            "a2": 0.592879605,
            "a3": 0.565907225,
            "a4": 0.509555985,
            "a5": 0.568452381,
        },
        "expected_chs_layer1": {
            "a1": 0.552926,
            "a2": 0.592880,
            "a3": 0.565907,
            "a4": 0.509556,
            "a5": 0.568452,
        },
    }


def test_hand_computed_fixture_step1_difficulty(hand_computed_fixture):
    """Step 1: Verify task difficulties against exact manual calculations."""
    f = hand_computed_fixture
    d = difficulty(f["interactions"], f["agents"], f["P"])

    for tid, exp_val in f["expected_difficulty"].items():
        assert math.isclose(d[tid], exp_val, rel_tol=1e-7, abs_tol=1e-7), (
            f"Difficulty mismatch on task {tid}: got {d[tid]}, expected {exp_val}"
        )


def test_hand_computed_fixture_step2_direct_scores(hand_computed_fixture):
    """Step 2: Verify direct evidence and shrinkage against exact manual calculations."""
    f = hand_computed_fixture
    d = difficulty(f["interactions"], f["agents"], f["P"])
    D_prime, n_a, C_a = direct_scores(f["interactions"], d, f["P"], f["as_of"])

    # All single attempts per task => consistency C_a must be 1.0
    for aid in ["a1", "a2", "a3", "a4", "a5"]:
        assert C_a.get(aid, 1.0) == 1.0

    for aid, exp_val in f["expected_D_prime"].items():
        assert math.isclose(D_prime.get(aid, 0.568452381), exp_val, rel_tol=1e-6, abs_tol=1e-6), (
            f"D_prime mismatch on agent {aid}: got {D_prime.get(aid)}, expected {exp_val}"
        )


def test_hand_computed_fixture_final_chs_layer1(hand_computed_fixture):
    """Step 5: Verify final composite score with no ratings matches Layer 1 exact scores."""
    f = hand_computed_fixture
    scores = chs(f["interactions"], f["agents"], ratings=None, P=f["P"], as_of=f["as_of"])

    for aid, exp_val in f["expected_chs_layer1"].items():
        assert scores[aid] == exp_val, f"CHS mismatch on {aid}: got {scores[aid]}, expected {exp_val}"


def test_consistency_variance_penalty():
    """Verify that inconsistent quality across multiple attempts on a task penalizes C_a."""
    as_of = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    P = CHSParams()
    agents = [{"agent_id": "volatile_agent", "provider": "p", "model": "m", "stake": 10}]
    
    # 2 attempts on task t1: 1.0 and 0.0 => mean=0.5, pop std = 0.5
    # C_a = clip(1 - 2 * 0.5, 0, 1) = 0.0!
    interactions = [
        {"agent_id": "volatile_agent", "task_id": "t1", "quality_score": 1.0, "timestamp": as_of},
        {"agent_id": "volatile_agent", "task_id": "t1", "quality_score": 0.0, "timestamp": as_of},
    ]

    d = difficulty(interactions, agents, P)
    D_prime, n_a, C_a = direct_scores(interactions, d, P, as_of)

    assert C_a["volatile_agent"] == 0.0
    score = chs(interactions, agents, None, P, as_of)
    assert score["volatile_agent"] == 0.0, "Inconsistent agent with C_a=0 must receive CHS=0.0"


def test_trust_propagation_and_defense():
    """Verify Steps 3 & 4: mutual rating ring triggers defense penalty pi_max."""
    as_of = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    P = CHSParams(N_iter=50, kappa1=0.5, kappa2=0.3, pi_max=0.8)

    agents = [
        {"agent_id": "colluder_1", "provider": "p1", "model": "m1", "stake": 50},
        {"agent_id": "colluder_2", "provider": "p2", "model": "m2", "stake": 50},
        {"agent_id": "honest",     "provider": "p3", "model": "m3", "stake": 50},
    ]

    interactions = [
        {"agent_id": "colluder_1", "task_id": "t1", "quality_score": 0.8, "timestamp": as_of},
        {"agent_id": "colluder_2", "task_id": "t1", "quality_score": 0.8, "timestamp": as_of},
        {"agent_id": "honest",     "task_id": "t1", "quality_score": 0.8, "timestamp": as_of},
    ]

    # Mutual ratings between colluder_1 and colluder_2 (both give 1.0)
    ratings = [
        {"rater_id": "colluder_1", "ratee_id": "colluder_2", "rating": 1.0},
        {"rater_id": "colluder_2", "ratee_id": "colluder_1", "rating": 1.0},
    ]

    pi = defense(ratings, agents, P)

    # For colluder_1: 100% incoming from colluder_2, who it also rates 1.0 >= 0.5 => m=1.0, H=1.0^2=1.0
    # penalty = min(0.8, 0.5*1.0 + 0.3*1.0) = 0.8
    assert math.isclose(pi["colluder_1"], 0.8, abs_tol=1e-7)
    assert math.isclose(pi["colluder_2"], 0.8, abs_tol=1e-7)
    assert pi["honest"] == 0.0

    scores = chs(interactions, agents, ratings, P, as_of)
    assert scores["colluder_1"] < scores["honest"], "Collusion ring must be penalized below honest agent"


def test_determinism_and_shuffle_invariance(hand_computed_fixture):
    """Verify determinism: shuffling input lists produces identical output to 6 decimals."""
    f = hand_computed_fixture
    score_1 = chs(f["interactions"], f["agents"], None, f["P"], f["as_of"])

    # Shuffle interactions and agents
    shuffled_inters = list(f["interactions"])
    shuffled_agents = list(f["agents"])
    random.seed(42)
    random.shuffle(shuffled_inters)
    random.shuffle(shuffled_agents)

    score_2 = chs(shuffled_inters, shuffled_agents, None, f["P"], f["as_of"])

    assert score_1 == score_2, "CHS must be strictly order-invariant regardless of input list permutation"


def test_clone_invariance_on_difficulty(hand_computed_fixture):
    """
    Step 1 family deduplication test:
    Adding K clones of one agent with the same model family must NOT change task difficulties.
    """
    f = hand_computed_fixture
    d_original = difficulty(f["interactions"], f["agents"], f["P"])

    # Clone a1 5 times under same family (gemini, flash) with identical attempts on t1
    clones = list(f["agents"])
    clone_inters = list(f["interactions"])
    for i in range(1, 6):
        cid = f"a1_clone_{i}"
        clones.append({"agent_id": cid, "provider": "gemini", "model": "flash", "stake": 10})
        clone_inters.append({"agent_id": cid, "task_id": "t1", "quality_score": 1.0, "timestamp": f["as_of"]})

    d_with_clones = difficulty(clone_inters, clones, f["P"])

    for tid in d_original:
        assert math.isclose(d_original[tid], d_with_clones[tid], abs_tol=1e-9), (
            f"Task {tid} difficulty changed when clones were injected: {d_original[tid]} vs {d_with_clones[tid]}"
        )


def test_edge_cases():
    """Verify edge cases: empty interactions, all-zero ratings, single-family task."""
    as_of = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    P = CHSParams()

    agents = [
        {"agent_id": "a1", "provider": "gemini", "model": "flash", "stake": 10},
        {"agent_id": "a2", "provider": "groq", "model": "llama3", "stake": 20},
    ]

    # 1. Zero interactions
    empty_scores = chs([], agents, None, P, as_of)
    assert len(empty_scores) == 2
    assert all(s >= 0.0 for s in empty_scores.values())

    # 2. All-zero ratings
    inters = [
        {"agent_id": "a1", "task_id": "t1", "quality_score": 1.0, "timestamp": as_of},
        {"agent_id": "a2", "task_id": "t1", "quality_score": 0.5, "timestamp": as_of},
    ]
    zero_ratings = [
        {"rater_id": "a1", "ratee_id": "a2", "rating": 0.0},
        {"rater_id": "a2", "ratee_id": "a1", "rating": 0.0},
    ]
    scores_zero_ratings = chs(inters, agents, zero_ratings, P, as_of)
    assert len(scores_zero_ratings) == 2
    assert scores_zero_ratings["a1"] > scores_zero_ratings["a2"]


def test_params_loader_and_hash():
    """Verify loading config/chs_params.yaml and computing deterministic params_hash."""
    params, p_hash = load_chs_params()
    assert params.version == "1.0.0"
    assert len(p_hash) == 64
    assert isinstance(p_hash, str)

    # Recomputing hash on same params yields identical hash
    p_hash_2 = compute_params_hash(params)
    assert p_hash == p_hash_2


def test_chsscorer_wrapper_integration(hand_computed_fixture):
    """Verify CHSScorer class conforms to BaseReputation interface."""
    f = hand_computed_fixture
    scorer = CHSScorer()
    scores = scorer.compute(
        interactions=f["interactions"],
        agents=f["agents"],
        reference_time=f["as_of"],
    )
    assert len(scores) == 5
    assert all(0.0 <= s <= 1.0 for s in scores.values())
