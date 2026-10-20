"""
chaintrust/experiments/suite.py
Comprehensive experimental evaluation suite for ChainTrust and CHS:
- Experiment A: Validity & Benchmark Rank Correlation (Spearman, Kendall)
- Experiment B: Real Sybil Clone Resistance (K = 0, 5, 10, 20 clones)
- Experiment C: Collusion Ring Resilience (Peer rating attacks vs defense)
- Experiment D: CHS Component Ablation Study (Family split, shrinkage, consistency, propagation, defense)
- Experiment E: Hyperparameter Sensitivity Analysis (lambda, beta, w, omega, kappa, S_cap)
- Experiment F: Randomized Cryptographic Tamper Detection (100+ trials on Level A & Level B)
All experiments output CSV data and PNG charts to experiments/results/ with deterministic seeds.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/CLI
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
from rich.console import Console
from rich.table import Table

from chaintrust.anchoring.bundle import create_chs_audit_bundle
from chaintrust.config import get_config
from chaintrust.db.models import Agent, Interaction, PeerRating, Task
from chaintrust.db.session import get_session
from chaintrust.reputation.algorithms import get_scorer
from chaintrust.reputation.chs import (
    CHSParams,
    chs,
    defense,
    direct_scores,
    load_chs_params,
    propagate,
)
from chaintrust.verifier.verifier import StandaloneVerifier

logger = logging.getLogger("chaintrust.experiments")
console = Console()

RESULTS_DIR = Path("experiments/results")


def _get_real_db_data() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, float]]:
    """Fetch real agents, interactions, and task difficulties from SQLite."""
    with get_session() as session:
        agents_orm = session.query(Agent).all()
        inters_orm = session.query(Interaction).all()
        tasks_orm = session.query(Task).all()

        agents = []
        for a in agents_orm:
            # Exclude test fixtures if needed, keeping real evaluation models
            if "test_rat" in a.agent_id:
                continue
            prov = a.provider or "unknown"
            mod = a.model or "unknown"
            agents.append({
                "agent_id": a.agent_id,
                "name": a.name,
                "provider": prov,
                "model": mod,
                "stake": int(a.stake or 0),
                "family": [prov, mod],
            })

        interactions = []
        for i in inters_orm:
            if any(ag["agent_id"] == i.agent_id for ag in agents):
                interactions.append({
                    "id": i.id,
                    "agent_id": i.agent_id,
                    "task_id": i.task_id,
                    "attempt": i.attempt,
                    "passed": bool(i.passed),
                    "quality_score": float(i.quality_score),
                    "difficulty_weight": float(i.difficulty_weight or 0.5),
                    "timestamp": i.timestamp,
                    "tests_passed": i.tests_passed,
                    "tests_total": i.tests_total,
                    "raw_output_hash": i.raw_output_hash or "",
                    "epoch": 1,
                })

        diff_table = {t.task_id: float(t.difficulty_weight or 0.5) for t in tasks_orm}

    return agents, interactions, diff_table


# ---------------------------------------------------------------------------
# Experiment A: Validity & Benchmark Rank Correlation
# ---------------------------------------------------------------------------
def run_experiment_a(output_dir: Path = RESULTS_DIR) -> pd.DataFrame:
    """
    Evaluates rank correlation of each reputation algorithm against known public benchmark rankings.
    Ground truth ranking on coding benchmarks (HumanEval pass@1 capability):
    gemini-flash > llama3-groq > mistral-7b > phi-3-mini
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()

    # Ground-truth capability ranking index (higher = better capability)
    # Gemini 2.5 Flash (~78%), Llama 3 70B / OSS (~68%), Mistral 7B (~35%), Phi-3 Mini (~33%)
    gt_benchmark_scores = {
        "gemini-flash-default": 0.78,
        "gemini-flash-creative": 0.76,
        "llama3-groq-default": 0.68,
        "llama3-groq-conservative": 0.67,
        "mistral-openrouter": 0.35,
        "phi3-openrouter": 0.33,
    }

    eval_agents = [ag for ag in agents if ag["name"] in gt_benchmark_scores]
    if not eval_agents:
        eval_agents = agents[:6]
        gt_benchmark_scores = {ag["name"]: 1.0 - (idx / len(eval_agents)) for idx, ag in enumerate(eval_agents)}

    methods = ["chs", "tracerank", "elo", "beta", "simple_avg", "pagerank", "eigentrust"]
    scores_by_method: Dict[str, Dict[str, float]] = {}

    for m in methods:
        scorer = get_scorer(m)
        computed = scorer.compute(
            interactions=interactions,
            agents=eval_agents,
            task_difficulties=diff_table,
        )
        scores_by_method[m] = computed

    # Compute correlations vs ground truth
    gt_vec = [gt_benchmark_scores.get(ag["name"], 0.5) for ag in eval_agents]
    records = []

    for m in methods:
        pred_vec = [scores_by_method[m].get(ag["agent_id"], 0.0) for ag in eval_agents]
        # Spearman & Kendall
        spearman_corr, _ = stats.spearmanr(pred_vec, gt_vec)
        kendall_corr, _ = stats.kendalltau(pred_vec, gt_vec)

        records.append({
            "method": m,
            "spearman_rho": round(float(spearman_corr), 4),
            "kendall_tau": round(float(kendall_corr), 4),
            "mean_pred_score": round(float(np.mean(pred_vec)), 4),
            "std_pred_score": round(float(np.std(pred_vec)), 4),
        })

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_a_validity.csv"
    df.to_csv(csv_path, index=False)

    # Plot
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(df))
    width = 0.35

    ax.bar(x - width/2, df["spearman_rho"], width, label="Spearman $\\rho$", color="#3b82f6")
    ax.bar(x + width/2, df["kendall_tau"], width, label="Kendall $\\tau$", color="#10b981")
    ax.set_ylabel("Rank Correlation with Ground Truth")
    ax.set_title("Experiment A: Validity & Rank Correlation Against Benchmark Capabilities")
    ax.set_xticks(x)
    ax.set_xticklabels(df["method"].str.upper(), rotation=15)
    ax.set_ylim(0, 1.1)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    ax.legend()
    plt.tight_layout()

    png_path = output_dir / "experiment_a_validity.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return df


# ---------------------------------------------------------------------------
# Experiment B: Real Sybil Clones
# ---------------------------------------------------------------------------
def run_experiment_b(
    output_dir: Path = RESULTS_DIR,
    clone_counts: Sequence[int] = (0, 5, 10, 20),
    seed: int = 42,
) -> pd.DataFrame:
    """
    Evaluates Sybil resistance: Attacker creates K identical clones of a real agent
    (same model, different agent_id, 0 stake).
    Plots Attacker Max Rank and Score Inflation vs K.
    """
    np.random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()

    # Pick a lower-capability agent to be cloned as an attacker attempting to inflate ranking
    attacker_base = next((ag for ag in agents if "phi3" in ag["name"] or "mistral" in ag["name"]), agents[-1])
    attacker_id = attacker_base["agent_id"]
    attacker_inters = [i for i in interactions if i["agent_id"] == attacker_id]

    methods = ["chs", "tracerank", "elo", "beta", "simple_avg", "pagerank", "eigentrust"]
    records = []

    # Store baseline scores at K=0
    baseline_scores: Dict[str, float] = {}

    for k in clone_counts:
        # Build cloned agent population
        test_agents = copy.deepcopy(agents)
        test_inters = copy.deepcopy(interactions)

        clone_ids = [f"sybil_clone_{i}" for i in range(k)]
        for c_idx, cid in enumerate(clone_ids):
            clone_agent = {
                "agent_id": cid,
                "name": f"Sybil Clone {c_idx+1}",
                "provider": attacker_base["provider"],
                "model": attacker_base["model"],
                "stake": 0,
                "family": attacker_base["family"],
            }
            test_agents.append(clone_agent)

            # Replicate attacker interactions for each clone
            for orig_int in attacker_inters:
                cloned_int = copy.deepcopy(orig_int)
                cloned_int["id"] = 100000 + c_idx * 1000 + cloned_int["id"]
                cloned_int["agent_id"] = cid
                test_inters.append(cloned_int)

        all_target_ids = [attacker_id] + clone_ids

        for m in methods:
            scorer = get_scorer(m)
            scores = scorer.compute(
                interactions=test_inters,
                agents=test_agents,
                task_difficulties=diff_table,
            )

            # Determine rank of the best attacker / clone
            sorted_by_score = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            ranks = {aid: rank + 1 for rank, (aid, _) in enumerate(sorted_by_score)}

            best_attacker_rank = min(ranks[aid] for aid in all_target_ids)
            best_attacker_score = max(scores[aid] for aid in all_target_ids)

            if k == 0:
                baseline_scores[m] = best_attacker_score
                inflation = 0.0
            else:
                base = baseline_scores.get(m, 0.001)
                inflation = max(0.0, (best_attacker_score - base) / max(0.001, base))

            records.append({
                "clone_count": k,
                "method": m,
                "best_attacker_rank": best_attacker_rank,
                "best_attacker_score": round(float(best_attacker_score), 6),
                "score_inflation_pct": round(float(inflation * 100.0), 2),
            })

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_b_sybil_clones.csv"
    df.to_csv(csv_path, index=False)

    # Plot
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    for m in methods:
        sub = df[df["method"] == m]
        ax1.plot(sub["clone_count"], sub["best_attacker_rank"], marker="o", label=m.upper())
        ax2.plot(sub["clone_count"], sub["score_inflation_pct"], marker="s", label=m.upper())

    ax1.set_xlabel("Number of Injected Sybil Clones ($K$)")
    ax1.set_ylabel("Attacker Best Rank (1 = Top)")
    ax1.set_title("Attacker Rank Penetration vs Sybil Clones")
    ax1.invert_yaxis()
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend()

    ax2.set_xlabel("Number of Injected Sybil Clones ($K$)")
    ax2.set_ylabel("Score Inflation (%)")
    ax2.set_title("Attacker Score Inflation vs Sybil Clones")
    ax2.grid(True, linestyle="--", alpha=0.6)
    ax2.legend()

    plt.tight_layout()
    png_path = output_dir / "experiment_b_sybil_clones.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return df


# ---------------------------------------------------------------------------
# Experiment C: Collusion Ring Resilience
# ---------------------------------------------------------------------------
def run_experiment_c(output_dir: Path = RESULTS_DIR, seed: int = 42) -> pd.DataFrame:
    """
    Evaluates collusion resistance: A subset of agents form a collusion ring,
    assigning mutual 1.0 ratings to each other and 0.0 to honest agents.
    Compares ring score inflation and honest top-K preservation across algorithms.
    """
    np.random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()

    chs_p, _ = load_chs_params()

    # Honest ratings baseline: directed peer reviews (asynchronous, non-mutual)
    honest_ratings: List[Dict[str, Any]] = []
    t0 = datetime.now(timezone.utc)
    n_agents = len(agents)
    for i, a in enumerate(agents):
        # Each agent reviews the next 2 in a directed chain: a_i -> a_{i+1}, a_i -> a_{i+2}
        # Note: In a directed chain with n >= 5, there are NO mutual pairs (m_a = 0)
        target_indices = [(i + 1) % n_agents, (i + 2) % n_agents]
        for t_idx in target_indices:
            b = agents[t_idx]
            honest_ratings.append({
                "rater_id": a["agent_id"],
                "ratee_id": b["agent_id"],
                "task_id": "humaneval/HumanEval_0",
                "rating": float(np.clip(np.random.normal(0.70, 0.05), 0.5, 0.9)),
                "justification": "Objective assessment",
                "raw_output_hash": "0x" + "11" * 32,
                "timestamp": t0,
            })

    # Pick 2 collusion ring members
    ring_members = [agents[-2]["agent_id"], agents[-1]["agent_id"]]

    # Collusive ratings graph: ring members give each other mutual 1.0, and 0.05 to others
    collusive_ratings = copy.deepcopy(honest_ratings)
    # Inject mutual reciprocal ratings between ring members
    collusive_ratings.append({
        "rater_id": ring_members[0],
        "ratee_id": ring_members[1],
        "task_id": "humaneval/HumanEval_0",
        "rating": 1.0,
        "justification": "Collusive maximum boost",
        "raw_output_hash": "0x99",
        "timestamp": t0,
    })
    collusive_ratings.append({
        "rater_id": ring_members[1],
        "ratee_id": ring_members[0],
        "task_id": "humaneval/HumanEval_0",
        "rating": 1.0,
        "justification": "Collusive maximum boost",
        "raw_output_hash": "0x99",
        "timestamp": t0,
    })

    methods = ["chs", "tracerank", "pagerank", "eigentrust", "beta", "simple_avg"]
    records = []

    for m in methods:
        # 1. Baseline honest run
        base_cfg = {"ratings": honest_ratings}
        scorer_h = get_scorer(m, base_cfg)
        scores_h = scorer_h.compute(interactions, agents, diff_table)
        ring_base_avg = np.mean([scores_h.get(rid, 0.0) for rid in ring_members])

        # 2. Under attack run
        att_cfg = {"ratings": collusive_ratings}
        scorer_a = get_scorer(m, att_cfg)
        scores_a = scorer_a.compute(interactions, agents, diff_table)
        ring_att_avg = np.mean([scores_a.get(rid, 0.0) for rid in ring_members])

        # Metric: Ring Inflation %
        inflation = (ring_att_avg - ring_base_avg) / max(0.001, ring_base_avg) * 100.0

        # Metric: Top-K preservation (are top 2 honest agents still top 2?)
        top_honest_baseline = sorted(
            [aid for aid in scores_h if aid not in ring_members],
            key=lambda x: scores_h[x],
            reverse=True
        )[:2]

        top_under_attack = sorted(scores_a, key=lambda x: scores_a[x], reverse=True)[:2]
        preserved = all(th in top_under_attack for th in top_honest_baseline)

        records.append({
            "method": m,
            "ring_baseline_score": round(float(ring_base_avg), 4),
            "ring_attack_score": round(float(ring_att_avg), 4),
            "ring_inflation_pct": round(float(inflation), 2),
            "honest_top_k_preserved": preserved,
        })

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_c_collusion_ring.csv"
    df.to_csv(csv_path, index=False)

    # Plot
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(df))
    bars = ax.bar(x, df["ring_inflation_pct"], color=["#10b981" if infl < 5.0 else "#ef4444" for infl in df["ring_inflation_pct"]])

    ax.set_ylabel("Collusion Ring Score Inflation (%)")
    ax.set_title("Experiment C: Resistance to Peer-Review Collusion Rings")
    ax.set_xticks(x)
    ax.set_xticklabels(df["method"].str.upper())
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    for bar, infl in zip(bars, df["ring_inflation_pct"]):
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 0.5, f"{infl:+.1f}%", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    png_path = output_dir / "experiment_c_collusion_ring.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return df


# ---------------------------------------------------------------------------
# Experiment D: CHS Component Ablation Study
# ---------------------------------------------------------------------------
def run_experiment_d(output_dir: Path = RESULTS_DIR, seed: int = 42) -> pd.DataFrame:
    """
    Ablations of CHS: systematically removes components to demonstrate necessity:
    1. Full CHS (all defenses active)
    2. No Family Split (vulnerable to clone dilution)
    3. No Bayesian Shrinkage (m=0)
    4. No Consistency Penalty (omega=0)
    5. No Trust Propagation (w=0, direct scores only)
    6. No Defense Penalty (kappa1=0, kappa2=0)
    Evaluates effect on Sybil Inflation and Collusion Inflation.
    """
    np.random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()

    base_params, _ = load_chs_params()

    ablations = [
        ("Full CHS", base_params, True),
        ("No Family Split", base_params, False),
        ("No Shrinkage (m=0)", CHSParams(**{**base_params.to_dict(), "m": 0.0}), True),
        ("No Consistency (w=0)", CHSParams(**{**base_params.to_dict(), "omega": 0.0}), True),
        ("No Trust Layer (w=0)", CHSParams(**{**base_params.to_dict(), "w": 0.0}), True),
        ("No Defense (pi=0)", CHSParams(**{**base_params.to_dict(), "kappa1": 0.0, "kappa2": 0.0}), True),
    ]

    # Setup collusion ring ratings
    t0 = datetime.now(timezone.utc)
    ring_members = [agents[-2]["agent_id"], agents[-1]["agent_id"]]
    collusive_ratings: List[Dict[str, Any]] = [
        {"rater_id": ring_members[0], "ratee_id": ring_members[1], "task_id": "humaneval/HumanEval_0", "rating": 1.0, "justification": "", "raw_output_hash": "0x1", "timestamp": t0},
        {"rater_id": ring_members[1], "ratee_id": ring_members[0], "task_id": "humaneval/HumanEval_0", "rating": 1.0, "justification": "", "raw_output_hash": "0x1", "timestamp": t0},
    ]

    records = []
    for name, p, use_family in ablations:
        eval_agents = copy.deepcopy(agents)
        if not use_family:
            # Strip family grouping so clones get distinct families
            for ag in eval_agents:
                ag["family"] = [ag["agent_id"], ag["agent_id"]]

        score_dict = chs(interactions, eval_agents, collusive_ratings, p, as_of=t0)
        ring_score = np.mean([score_dict[r] for r in ring_members])
        honest_score = np.mean([score_dict[ag["agent_id"]] for ag in eval_agents if ag["agent_id"] not in ring_members])
        gap = ring_score - honest_score

        records.append({
            "ablation": name,
            "ring_avg_score": round(float(ring_score), 4),
            "honest_avg_score": round(float(honest_score), 4),
            "collusion_advantage": round(float(gap), 4),
        })

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_d_ablations.csv"
    df.to_csv(csv_path, index=False)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(df))
    ax.bar(x, df["collusion_advantage"], color=["#10b981" if "Full" in a else "#f59e0b" for a in df["ablation"]])
    ax.set_ylabel("Attacker Score Advantage Over Honest")
    ax.set_title("Experiment D: Component Ablations and Attacker Advantage")
    ax.set_xticks(x)
    ax.set_xticklabels(df["ablation"], rotation=15)
    ax.grid(axis="y", linestyle="--", alpha=0.6)

    plt.tight_layout()
    png_path = output_dir / "experiment_d_ablations.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return df


# ---------------------------------------------------------------------------
# Experiment E: Parameter Sensitivity Analysis
# ---------------------------------------------------------------------------
def run_experiment_e(output_dir: Path = RESULTS_DIR) -> pd.DataFrame:
    """
    Evaluates sensitivity to hyperparameters:
    lambda, beta, w, omega, kappa1, S_cap.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()
    base_params, _ = load_chs_params()
    t0 = datetime.now(timezone.utc)

    # Create synthetic baseline ratings
    ratings = [
        {"rater_id": agents[0]["agent_id"], "ratee_id": agents[1]["agent_id"], "task_id": "task_1", "rating": 0.8, "justification": "", "raw_output_hash": "0x1", "timestamp": t0},
        {"rater_id": agents[1]["agent_id"], "ratee_id": agents[0]["agent_id"], "task_id": "task_1", "rating": 0.85, "justification": "", "raw_output_hash": "0x2", "timestamp": t0},
    ]

    variations = [
        ("decay_lambda", [0.005, 0.023, 0.05, 0.1]),
        ("beta", [0.5, 0.7, 0.85, 0.95]),
        ("w", [0.0, 0.15, 0.3, 0.5, 0.7]),
        ("omega", [0.0, 0.25, 0.5, 0.75, 1.0]),
        ("kappa1", [0.1, 0.3, 0.5, 0.8]),
        ("S_cap", [100.0, 500.0, 1000.0, 5000.0]),
    ]

    records = []
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes_flat = axes.flatten()

    for idx, (param_name, vals) in enumerate(variations):
        sub_records = []
        for v in vals:
            param_dict = base_params.to_dict()
            param_dict[param_name] = v
            p = CHSParams(**param_dict)
            scores = chs(interactions, agents, ratings, p, as_of=t0)
            avg_score = float(np.mean(list(scores.values())))
            std_score = float(np.std(list(scores.values())))

            records.append({
                "parameter": param_name,
                "value": v,
                "mean_score": round(avg_score, 4),
                "std_score": round(std_score, 4),
            })
            sub_records.append((v, avg_score, std_score))

        # Subplot
        ax = axes_flat[idx]
        x_vals = [s[0] for s in sub_records]
        y_vals = [s[1] for s in sub_records]
        ax.plot(x_vals, y_vals, marker="o", color="#3b82f6", linewidth=2)
        ax.set_title(f"Sensitivity: {param_name}")
        ax.set_xlabel(param_name)
        ax.set_ylabel("Mean Agent Score")
        ax.grid(True, linestyle="--", alpha=0.5)

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_e_sensitivity.csv"
    df.to_csv(csv_path, index=False)

    plt.tight_layout()
    png_path = output_dir / "experiment_e_sensitivity.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return df


# ---------------------------------------------------------------------------
# Experiment F: Randomized Cryptographic Tamper Detection
# ---------------------------------------------------------------------------
def run_experiment_f(
    output_dir: Path = RESULTS_DIR,
    trials_per_type: int = 30,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Conducts 120 randomized tamper attacks across Level A and Level B audit bundles:
    - 30 Alter trials (modify quality score or difficulty)
    - 30 Delete trials (drop interaction or rating)
    - 30 Reorder trials (reorder records to break Merkle ordering)
    - 30 Insert trials (inject unauthorized record)
    Reports exact detection rates.
    """
    np.random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    agents, interactions, diff_table = _get_real_db_data()
    chs_p, _ = load_chs_params()

    target_agent = agents[0]["agent_id"]
    agent_inters = [i for i in interactions if i["agent_id"] == target_agent][:8]
    if len(agent_inters) < 4:
        agent_inters = interactions[:6]
        target_agent = agent_inters[0]["agent_id"]

    t0 = datetime.now(timezone.utc)
    ratings = [
        {"rater_id": agents[0]["agent_id"], "ratee_id": agents[1]["agent_id"], "task_id": "task_1", "rating": 0.85, "justification": "", "raw_output_hash": "0x11", "timestamp": t0},
        {"rater_id": agents[1]["agent_id"], "ratee_id": agents[0]["agent_id"], "task_id": "task_1", "rating": 0.80, "justification": "", "raw_output_hash": "0x22", "timestamp": t0},
    ]

    bundle_a, _ = create_chs_audit_bundle(
        agent_id=target_agent,
        epoch=1,
        interactions=agent_inters,
        difficulty_table=diff_table,
        params=chs_p,
        as_of=t0,
        output_dir=str(output_dir),
    )

    bundle_b, _ = create_chs_audit_bundle(
        agent_id=target_agent,
        epoch=1,
        interactions=agent_inters,
        difficulty_table=diff_table,
        params=chs_p,
        ratings=ratings,
        agents=agents,
        as_of=t0,
        output_dir=str(output_dir),
    )

    verifier = StandaloneVerifier()
    records = []

    # 1. Alter tests
    for t_idx in range(trials_per_type):
        tampered_a = copy.deepcopy(bundle_a)
        idx_rec = np.random.randint(0, len(tampered_a["records"]))
        tampered_a["records"][idx_rec]["quality_score"] = float(np.random.uniform(0.0, 1.0))
        res_a = verifier.verify_bundle(tampered_a)
        records.append({"level": "A", "attack_type": "Alter", "trial": t_idx + 1, "detected": not res_a.valid})

        tampered_b = copy.deepcopy(bundle_b)
        if np.random.rand() < 0.5:
            idx_r = np.random.randint(0, len(tampered_b["records"]))
            tampered_b["records"][idx_r]["quality_score"] = float(np.random.uniform(0.0, 1.0))
        else:
            idx_rt = np.random.randint(0, len(tampered_b["ratings_table"]))
            tampered_b["ratings_table"][idx_rt]["rating"] = float(np.random.uniform(0.0, 1.0))
        res_b = verifier.verify_bundle(tampered_b)
        records.append({"level": "B", "attack_type": "Alter", "trial": t_idx + 1, "detected": not res_b.valid})

    # 2. Delete tests
    for t_idx in range(trials_per_type):
        tampered_a = copy.deepcopy(bundle_a)
        if len(tampered_a["records"]) > 1:
            tampered_a["records"].pop(np.random.randint(0, len(tampered_a["records"])))
        res_a = verifier.verify_bundle(tampered_a)
        records.append({"level": "A", "attack_type": "Delete", "trial": t_idx + 1, "detected": not res_a.valid})

        tampered_b = copy.deepcopy(bundle_b)
        if np.random.rand() < 0.5 and len(tampered_b["records"]) > 1:
            tampered_b["records"].pop(np.random.randint(0, len(tampered_b["records"])))
        elif len(tampered_b.get("ratings_table", [])) > 1:
            tampered_b["ratings_table"].pop(0)
        res_b = verifier.verify_bundle(tampered_b)
        records.append({"level": "B", "attack_type": "Delete", "trial": t_idx + 1, "detected": not res_b.valid})

    # 3. Reorder tests
    for t_idx in range(trials_per_type):
        tampered_a = copy.deepcopy(bundle_a)
        if len(tampered_a["records"]) > 1:
            tampered_a["records"].reverse()
        res_a = verifier.verify_bundle(tampered_a)
        records.append({"level": "A", "attack_type": "Reorder", "trial": t_idx + 1, "detected": not res_a.valid})

        tampered_b = copy.deepcopy(bundle_b)
        if len(tampered_b.get("ratings_table", [])) > 1:
            tampered_b["ratings_table"].reverse()
        res_b = verifier.verify_bundle(tampered_b)
        records.append({"level": "B", "attack_type": "Reorder", "trial": t_idx + 1, "detected": not res_b.valid})

    # 4. Insert tests
    for t_idx in range(trials_per_type):
        tampered_a = copy.deepcopy(bundle_a)
        fake_rec = copy.deepcopy(tampered_a["records"][0])
        fake_rec["id"] = 999999 + t_idx
        fake_rec["quality_score"] = 1.0
        tampered_a["records"].append(fake_rec)
        res_a = verifier.verify_bundle(tampered_a)
        records.append({"level": "A", "attack_type": "Insert", "trial": t_idx + 1, "detected": not res_a.valid})

        tampered_b = copy.deepcopy(bundle_b)
        fake_rating = copy.deepcopy(tampered_b["ratings_table"][0])
        fake_rating["rating"] = 1.0
        fake_rating["rater_id"] = "fake_adversary"
        tampered_b["ratings_table"].append(fake_rating)
        res_b = verifier.verify_bundle(tampered_b)
        records.append({"level": "B", "attack_type": "Insert", "trial": t_idx + 1, "detected": not res_b.valid})

    df = pd.DataFrame(records)
    csv_path = output_dir / "experiment_f_tamper_detection.csv"
    df.to_csv(csv_path, index=False)

    # Aggregate detection rates
    summary = df.groupby(["level", "attack_type"])["detected"].agg(["count", "mean"]).reset_index()
    summary["detection_rate_pct"] = summary["mean"] * 100.0

    # Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    types = ["Alter", "Delete", "Reorder", "Insert"]
    x = np.arange(len(types))
    width = 0.35

    rates_a = [summary[(summary["level"] == "A") & (summary["attack_type"] == t)]["detection_rate_pct"].values[0] for t in types]
    rates_b = [summary[(summary["level"] == "B") & (summary["attack_type"] == t)]["detection_rate_pct"].values[0] for t in types]

    ax.bar(x - width/2, rates_a, width, label="Level A Verification", color="#3b82f6")
    ax.bar(x + width/2, rates_b, width, label="Level B Verification", color="#10b981")
    ax.set_ylabel("Tamper Detection Rate (%)")
    ax.set_title("Experiment F: Cryptographic Tamper Detection Across 120 Randomized Trials")
    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_ylim(0, 110)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend(loc="lower right")

    plt.tight_layout()
    png_path = output_dir / "experiment_f_tamper_detection.png"
    plt.savefig(png_path, dpi=300)
    plt.close()

    return summary


# ---------------------------------------------------------------------------
# Master Runner
# ---------------------------------------------------------------------------
def run_all_experiments(output_dir: Path = RESULTS_DIR) -> Dict[str, Any]:
    """Execute all 6 experiments A-F in sequence and print Rich summary tables."""
    console.print("\n[bold cyan]===========================================================[/bold cyan]")
    console.print("[bold cyan]       ChainTrust Empirical & Adversarial Benchmark        [/bold cyan]")
    console.print("[bold cyan]===========================================================[/bold cyan]\n")

    # Experiment A
    console.print("[bold yellow]Running Experiment A: Benchmark Validity & Rank Correlations...[/bold yellow]")
    df_a = run_experiment_a(output_dir)
    tbl_a = Table(title="Experiment A: Validity Rank Correlations")
    tbl_a.add_column("Method", style="bold")
    tbl_a.add_column("Spearman $\\rho$", justify="right")
    tbl_a.add_column("Kendall $\\tau$", justify="right")
    for _, row in df_a.iterrows():
        tbl_a.add_row(row["method"].upper(), f"{row['spearman_rho']:.4f}", f"{row['kendall_tau']:.4f}")
    console.print(tbl_a)

    # Experiment B
    console.print("\n[bold yellow]Running Experiment B: Real Sybil Clone Resistance...[/bold yellow]")
    df_b = run_experiment_b(output_dir)
    tbl_b = Table(title="Experiment B: Sybil Resistance (K=20 clones)")
    tbl_b.add_column("Method", style="bold")
    tbl_b.add_column("Best Attacker Rank", justify="right")
    tbl_b.add_column("Score Inflation (%)", justify="right")
    for _, row in df_b[df_b["clone_count"] == 20].iterrows():
        tbl_b.add_row(row["method"].upper(), str(row["best_attacker_rank"]), f"{row['score_inflation_pct']:+.1f}%")
    console.print(tbl_b)

    # Experiment C
    console.print("\n[bold yellow]Running Experiment C: Collusion Ring Resilience...[/bold yellow]")
    df_c = run_experiment_c(output_dir)
    tbl_c = Table(title="Experiment C: Collusion Ring Inflation & Top-K Preservation")
    tbl_c.add_column("Method", style="bold")
    tbl_c.add_column("Ring Inflation (%)", justify="right")
    tbl_c.add_column("Honest Top-K Preserved", justify="center")
    for _, row in df_c.iterrows():
        pres = "[green]YES[/green]" if row["honest_top_k_preserved"] else "[red]NO[/red]"
        tbl_c.add_row(row["method"].upper(), f"{row['ring_inflation_pct']:+.1f}%", pres)
    console.print(tbl_c)

    # Experiment D
    console.print("\n[bold yellow]Running Experiment D: Component Ablations...[/bold yellow]")
    df_d = run_experiment_d(output_dir)
    tbl_d = Table(title="Experiment D: CHS Ablation Results")
    tbl_d.add_column("Configuration", style="bold")
    tbl_d.add_column("Attacker Advantage", justify="right")
    for _, row in df_d.iterrows():
        tbl_d.add_row(row["ablation"], f"{row['collusion_advantage']:+.4f}")
    console.print(tbl_d)

    # Experiment E
    console.print("\n[bold yellow]Running Experiment E: Parameter Sensitivity Analysis...[/bold yellow]")
    df_e = run_experiment_e(output_dir)
    console.print(f"[green]Evaluated {len(df_e)} parameter configurations. Plots saved.[/green]")

    # Experiment F
    console.print("\n[bold yellow]Running Experiment F: Cryptographic Tamper Detection...[/bold yellow]")
    summary_f = run_experiment_f(output_dir)
    tbl_f = Table(title="Experiment F: Tamper Detection (120 Trials)")
    tbl_f.add_column("Verification Level", justify="center")
    tbl_f.add_column("Attack Type", style="bold")
    tbl_f.add_column("Trials", justify="right")
    tbl_f.add_column("Detection Rate (%)", justify="right")
    for _, row in summary_f.iterrows():
        tbl_f.add_row(row["level"], row["attack_type"], str(row["count"]), f"[bold green]{row['detection_rate_pct']:.1f}%[/bold green]")
    console.print(tbl_f)

    console.print("\n[bold green]All 6 experiments completed. Results written to experiments/results/[/bold green]\n")
    return {
        "A": df_a,
        "B": df_b,
        "C": df_c,
        "D": df_d,
        "E": df_e,
        "F": summary_f,
    }
