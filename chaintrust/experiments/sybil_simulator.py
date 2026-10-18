"""
chaintrust/experiments/sybil_simulator.py
Sybil attack and collusion simulation framework for ChainTrust.
Evaluates the adversarial resilience of TraceRank compared to baselines
(simple_avg, weighted, pagerank, eigentrust).
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import scipy.stats as stats

from chaintrust.reputation.algorithms import compute_task_difficulties, get_scorer

logger = logging.getLogger("chaintrust.experiments")


@dataclass
class SybilExperimentResult:
    """Holds comparative resilience metrics for one experiment run."""
    clone_count: int
    algorithm_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # algorithm_metrics[method] = {
    #     "top_k_preserved": 1.0 or 0.0,
    #     "kendall_tau": float,
    #     "sybil_max_rank": int,
    #     "sybil_top_k_penetration": float,
    #     "honest_score_degradation": float,
    # }


class SybilSimulator:
    """
    Simulates Sybil identities and collusion attacks against reputation algorithms.
    """

    def __init__(
        self,
        top_k: int = 3,
        methods: Optional[Sequence[str]] = None,
    ):
        self.top_k = top_k
        self.methods = list(methods or ["simple_avg", "weighted", "pagerank", "eigentrust", "tracerank"])

    def create_synthetic_honest_population(
        self,
        num_honest: int = 6,
        tasks_per_agent: int = 20,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Creates synthetic honest agents with varied capabilities and stakes,
        along with an evaluation task suite.
        """
        honest_agents: List[Dict[str, Any]] = []
        for i in range(num_honest):
            stake = 50 if i == 0 else (20 if i < 3 else 5)
            honest_agents.append({
                "agent_id": f"honest_agent_{i}",
                "name": f"Honest Agent {i}",
                "stake": stake,
                "capability": 0.5 + 0.45 * (1.0 - (i / max(1, num_honest - 1))),  # 0.50 to 0.95
            })

        tasks = [f"task_{j}" for j in range(tasks_per_agent)]
        interactions: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        inter_id = 1
        for ag in honest_agents:
            cap = ag["capability"]
            for tid in tasks:
                # Task difficulty variance
                t_idx = int(tid.split("_")[1])
                t_diff = 0.2 + 0.7 * (t_idx / max(1, tasks_per_agent - 1))
                # Probability of pass
                p_pass = max(0.05, min(0.95, cap - (t_diff * 0.3)))
                passed = (np.random.rand() < p_pass)
                quality = 1.0 if passed else (0.2 + 0.5 * np.random.rand())

                interactions.append({
                    "id": inter_id,
                    "agent_id": ag["agent_id"],
                    "task_id": tid,
                    "attempt": 1,
                    "passed": bool(passed),
                    "quality_score": float(quality),
                    "difficulty_weight": float(t_diff),
                    "timestamp": now - timedelta(days=float(np.random.uniform(0, 10))),
                })
                inter_id += 1

        return honest_agents, interactions

    def inject_sybil_clones(
        self,
        honest_agents: Sequence[Dict[str, Any]],
        honest_interactions: Sequence[Dict[str, Any]],
        num_clones: int,
        attack_type: str = "easy_task_farming",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Injects Sybil clones:
        - Stake = 0
        - Tries to farm easy tasks or collude to manipulate rankings
        """
        if num_clones <= 0:
            return list(honest_agents), list(honest_interactions)

        all_agents = list(copy.deepcopy(honest_agents))
        all_interactions = list(copy.deepcopy(honest_interactions))

        max_id = max((x.get("id", 0) for x in all_interactions), default=0) + 1
        now = datetime.now(timezone.utc)

        sybil_agents: List[Dict[str, Any]] = []
        for c in range(num_clones):
            sid = f"sybil_{c}"
            sybil = {
                "agent_id": sid,
                "name": f"Sybil Clone {c}",
                "stake": 0,  # Zero stake
                "capability": 0.2,  # Low real capability
            }
            sybil_agents.append(sybil)
            all_agents.append(sybil)

        if attack_type == "easy_task_farming":
            # Sybils spam perfect scores on the easiest tasks (e.g. task_0, task_1)
            easy_tasks = ["task_0", "task_1", "task_2"]
            for syb in sybil_agents:
                for tid in easy_tasks:
                    all_interactions.append({
                        "id": max_id,
                        "agent_id": syb["agent_id"],
                        "task_id": tid,
                        "attempt": 1,
                        "passed": True,
                        "quality_score": 1.0,  # Faked 100% pass on easy tasks
                        "difficulty_weight": 0.2,
                        "timestamp": now,
                    })
                    max_id += 1

        elif attack_type == "collusion_ring":
            # Sybils cross-endorse or submit identical solutions
            tasks = [f"task_{j}" for j in range(5)]
            for syb in sybil_agents:
                for tid in tasks:
                    all_interactions.append({
                        "id": max_id,
                        "agent_id": syb["agent_id"],
                        "task_id": tid,
                        "attempt": 1,
                        "passed": True,
                        "quality_score": 0.95,
                        "difficulty_weight": 0.3,
                        "timestamp": now,
                    })
                    max_id += 1

        return all_agents, all_interactions

    def evaluate_resilience(
        self,
        honest_agents: Sequence[Dict[str, Any]],
        honest_interactions: Sequence[Dict[str, Any]],
        clone_counts: Sequence[int] = (0, 5, 10, 20),
        attack_type: str = "easy_task_farming",
    ) -> List[SybilExperimentResult]:
        """
        Runs the full evaluation benchmark across all methods and clone counts.
        """
        results: List[SybilExperimentResult] = []
        honest_ids = [ag["agent_id"] for ag in honest_agents]

        # 1. Baseline ground-truth reputation on honest population
        baseline_diffs = compute_task_difficulties(honest_interactions)
        baseline_ranks: Dict[str, List[str]] = {}
        for m in self.methods:
            scorer = get_scorer(m)
            scores = scorer.compute(honest_interactions, honest_agents, baseline_diffs)
            ranked = sorted(honest_ids, key=lambda aid: scores.get(aid, 0.0), reverse=True)
            baseline_ranks[m] = ranked

        # 2. Test each clone count
        for count in clone_counts:
            exp_result = SybilExperimentResult(clone_count=count)
            all_agents, all_inters = self.inject_sybil_clones(
                honest_agents, honest_interactions, num_clones=count, attack_type=attack_type
            )
            diffs = compute_task_difficulties(all_inters)

            for m in self.methods:
                scorer = get_scorer(m)
                post_scores = scorer.compute(all_inters, all_agents, diffs)

                all_ranked = sorted(
                    [a["agent_id"] for a in all_agents],
                    key=lambda aid: post_scores.get(aid, 0.0),
                    reverse=True,
                )

                # Honest subset rankings
                honest_post_ranked = [aid for aid in all_ranked if aid in honest_ids]

                # Check top-k preservation
                expected_top_k = set(baseline_ranks[m][:self.top_k])
                actual_top_k = set(all_ranked[:self.top_k])
                # Sybil penetration in top-k
                sybils_in_top_k = sum(1 for aid in all_ranked[:self.top_k] if aid not in honest_ids)
                top_k_preserved = 1.0 if sybils_in_top_k == 0 else 0.0

                # Kendall's tau correlation between honest agent relative ranks
                base_indices = [baseline_ranks[m].index(aid) for aid in honest_ids]
                post_indices = [honest_post_ranked.index(aid) for aid in honest_ids]
                tau, _ = stats.kendalltau(base_indices, post_indices)
                if np.isnan(tau):
                    tau = 1.0

                # Max rank achieved by a Sybil (1 = rank 1, higher is worse for attacker)
                sybil_ranks = [i + 1 for i, aid in enumerate(all_ranked) if aid not in honest_ids]
                sybil_max_rank = min(sybil_ranks) if sybil_ranks else len(all_ranked)

                exp_result.algorithm_metrics[m] = {
                    "top_k_preserved": float(top_k_preserved),
                    "kendall_tau": round(float(tau), 4),
                    "sybil_top_k_penetration": float(sybils_in_top_k / max(1, self.top_k)),
                    "sybil_best_rank": int(sybil_max_rank),
                }

            results.append(exp_result)

        return results
