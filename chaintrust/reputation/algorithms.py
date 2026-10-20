"""
chaintrust/reputation/algorithms.py
Implementation of 5 reputation scoring algorithms for real AI agent task histories:
1. simple_avg       - Unweighted mean of test pass rates (raw baseline)
2. weighted         - Difficulty-weighted and exponential time-decay baseline
3. pagerank         - Co-evaluation / bipartite graph PageRank baseline
4. eigentrust       - Peer-trust propagation with pre-trusted seed nodes
5. tracerank        - ChainTrust proprietary algorithm with dynamic task difficulty (d_t),
                      sublinear stake-weighted rater trust, temporal decay, and consistency multiplier.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import networkx as nx
import numpy as np


def compute_task_difficulties(
    interactions: Sequence[Any],
    d_min: float = 0.1,
    d_max: float = 1.0,
    smoothing: float = 1.0,
) -> Dict[str, float]:
    """
    Computes empirical difficulty weight d_t for each task with Laplace smoothing:
        d_t = 1.0 - (passed + smoothing) / (total + 2 * smoothing)
    clipped to [d_min, d_max].
    If no interactions exist for a task, defaults to 0.5.
    """
    task_stats: Dict[str, Dict[str, int]] = {}
    for inter in interactions:
        tid = getattr(inter, "task_id", None) or inter.get("task_id")
        passed = getattr(inter, "passed", None)
        if passed is None and isinstance(inter, dict):
            passed = inter.get("passed", False)
        if tid not in task_stats:
            task_stats[tid] = {"passed": 0, "total": 0}
        task_stats[tid]["total"] += 1
        if passed:
            task_stats[tid]["passed"] += 1

    difficulties: Dict[str, float] = {}
    for tid, stats in task_stats.items():
        total = stats["total"]
        passed = stats["passed"]
        pass_fraction = (passed + smoothing) / (total + 2.0 * smoothing)
        diff = 1.0 - pass_fraction
        diff = max(d_min, min(d_max, diff))
        difficulties[tid] = diff

    return difficulties


class BaseReputation(ABC):
    """Abstract base class for all reputation scoring algorithms."""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}

    @abstractmethod
    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        """
        Compute reputation score for each agent.
        Returns a dict mapping agent_id -> score in [0.0, 1.0].
        """
        pass


class SimpleAverage(BaseReputation):
    """
    Computes simple unweighted average of quality scores for each agent.
    Quality score is in [0, 1].
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("simple_avg", config)

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        scores: Dict[str, List[float]] = {}
        for ag in agents:
            aid = getattr(ag, "agent_id", None) or ag.get("agent_id")
            scores[aid] = []

        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            q = getattr(inter, "quality_score", None)
            if q is None and isinstance(inter, dict):
                q = inter.get("quality_score", 0.0)
            if aid in scores and q is not None:
                scores[aid].append(float(q))

        results: Dict[str, float] = {}
        for aid, q_list in scores.items():
            results[aid] = float(np.mean(q_list)) if q_list else 0.0
        return results


class WeightedHistory(BaseReputation):
    """
    Computes score using exponential time decay and task difficulty weights:
        w_i = d_t * exp(-ln(2) / half_life * age_days)
        score_a = sum(quality_i * w_i) / sum(w_i)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("weighted", config)
        self.half_life_days = float(self.config.get("half_life_days", 30.0))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        now = reference_time or datetime.now(timezone.utc)
        decay_rate = math.log(2.0) / max(self.half_life_days, 1e-6)

        weighted_sums: Dict[str, float] = {}
        weight_totals: Dict[str, float] = {}

        for ag in agents:
            aid = getattr(ag, "agent_id", None) or ag.get("agent_id")
            weighted_sums[aid] = 0.0
            weight_totals[aid] = 0.0

        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            if aid not in weighted_sums:
                continue

            tid = getattr(inter, "task_id", None) or inter.get("task_id")
            q = getattr(inter, "quality_score", None)
            if q is None and isinstance(inter, dict):
                q = inter.get("quality_score", 0.0)

            ts = getattr(inter, "timestamp", None) or (inter.get("timestamp") if isinstance(inter, dict) else None)
            if ts is None:
                age_days = 0.0
            else:
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except Exception:
                        ts = None
                if ts is None:
                    age_days = 0.0
                else:
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)

            d_t = (task_difficulties or {}).get(tid, 0.5)
            w = d_t * math.exp(-decay_rate * age_days)

            weighted_sums[aid] += float(q) * w
            weight_totals[aid] += w

        results: Dict[str, float] = {}
        for aid in weighted_sums:
            if weight_totals[aid] > 0:
                results[aid] = float(np.clip(weighted_sums[aid] / weight_totals[aid], 0.0, 1.0))
            else:
                results[aid] = 0.0
        return results


class PageRankScorer(BaseReputation):
    """
    Computes reputation on an agent-task bipartite graph using PageRank.
    Nodes are agents and tasks. Directed edges flow from tasks to agents weighted
    by agent performance (quality * difficulty), and feedback edges flow back.
    Final scores are extracted for agent nodes and min-max scaled to [0, 1].
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("pagerank", config)
        self.alpha = float(self.config.get("alpha", 0.85))
        self.max_iter = int(self.config.get("max_iter", 100))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        agent_ids = [getattr(ag, "agent_id", None) or ag.get("agent_id") for ag in agents]
        if not interactions:
            return {aid: 0.0 for aid in agent_ids}

        G = nx.DiGraph()
        for aid in agent_ids:
            G.add_node(f"agent:{aid}")

        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            tid = getattr(inter, "task_id", None) or inter.get("task_id")
            q = float(getattr(inter, "quality_score", None) if getattr(inter, "quality_score", None) is not None else (inter.get("quality_score", 0.0) if isinstance(inter, dict) else 0.0))
            d_t = (task_difficulties or {}).get(tid, 0.5)

            a_node = f"agent:{aid}"
            t_node = f"task:{tid}"
            G.add_node(t_node)

            weight = max(1e-4, q * d_t)
            # Edge from task to agent
            if G.has_edge(t_node, a_node):
                G[t_node][a_node]["weight"] += weight
            else:
                G.add_edge(t_node, a_node, weight=weight)

            # Bidirectional feedback edge so random walk doesn't get stuck
            back_weight = max(1e-4, (1.0 - q * 0.5) * d_t)
            if G.has_edge(a_node, t_node):
                G[a_node][t_node]["weight"] += back_weight
            else:
                G.add_edge(a_node, t_node, weight=back_weight)

        try:
            pr = nx.pagerank(G, alpha=self.alpha, max_iter=self.max_iter, weight="weight")
        except Exception:
            # Fallback to unweighted or uniform
            pr = {node: 1.0 / len(G) for node in G.nodes()}

        raw_agent_scores = {aid: pr.get(f"agent:{aid}", 0.0) for aid in agent_ids}
        vals = list(raw_agent_scores.values())
        max_val = max(vals) if vals else 1.0
        min_val = min(vals) if vals else 0.0

        if max_val > min_val:
            scaled = {aid: (raw_agent_scores[aid] - min_val) / (max_val - min_val) for aid in agent_ids}
        else:
            scaled = {aid: (1.0 if max_val > 0 else 0.0) for aid in agent_ids}
        return scaled


class EigenTrustScorer(BaseReputation):
    """
    Computes EigenTrust reputation scores using normalized local trust matrix
    and iterative power method with pre-trusted seed nodes.
    Pre-trusted agents are those with the highest stake (or first registered).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("eigentrust", config)
        self.alpha = float(self.config.get("alpha", 0.1))
        self.max_iter = int(self.config.get("max_iter", 100))
        self.tol = float(self.config.get("tol", 1e-6))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        agent_list = list(agents)
        n = len(agent_list)
        if n == 0:
            return {}
        agent_ids = [getattr(ag, "agent_id", None) or ag.get("agent_id") for ag in agent_list]
        idx_map = {aid: i for i, aid in enumerate(agent_ids)}

        # Pre-trusted vector p based on stake
        stakes = [float(getattr(ag, "stake", 0) or (ag.get("stake", 0) if isinstance(ag, dict) else 0)) for ag in agent_list]
        total_stake = sum(stakes)
        if total_stake > 0:
            p = np.array([s / total_stake for s in stakes], dtype=float)
        else:
            p = np.full(n, 1.0 / n, dtype=float)

        # Build pairwise co-occurrence / cross-task comparative evaluation matrix C
        # Agent i trusts agent j if agent j performs well on tasks where agent i also interacted
        task_perf: Dict[str, Dict[str, float]] = {}
        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            tid = getattr(inter, "task_id", None) or inter.get("task_id")
            q = float(getattr(inter, "quality_score", None) if getattr(inter, "quality_score", None) is not None else (inter.get("quality_score", 0.0) if isinstance(inter, dict) else 0.0))
            if tid not in task_perf:
                task_perf[tid] = {}
            task_perf[tid][aid] = max(task_perf[tid].get(aid, 0.0), q)

        C = np.zeros((n, n), dtype=float)
        for tid, perf in task_perf.items():
            for aid_i, q_i in perf.items():
                if aid_i not in idx_map:
                    continue
                i = idx_map[aid_i]
                for aid_j, q_j in perf.items():
                    if aid_j not in idx_map:
                        continue
                    j = idx_map[aid_j]
                    C[i, j] += q_j

        # Row normalize C
        row_sums = C.sum(axis=1)
        for i in range(n):
            if row_sums[i] > 0:
                C[i, :] /= row_sums[i]
            else:
                C[i, :] = p

        # Power iteration: t_{k+1} = (1 - alpha) * C^T * t_k + alpha * p
        t = p.copy()
        for _ in range(self.max_iter):
            t_next = (1.0 - self.alpha) * np.dot(C.T, t) + self.alpha * p
            norm = np.linalg.norm(t_next - t, 1)
            t = t_next
            if norm < self.tol:
                break

        # Normalize score to [0, 1] relative to theoretical max
        max_t = np.max(t) if len(t) > 0 else 1.0
        min_t = np.min(t) if len(t) > 0 else 0.0
        results: Dict[str, float] = {}
        if max_t > min_t:
            for i, aid in enumerate(agent_ids):
                results[aid] = float((t[i] - min_t) / (max_t - min_t))
        else:
            for i, aid in enumerate(agent_ids):
                results[aid] = float(t[i])
        return results


class TraceRankScorer(BaseReputation):
    """
    ChainTrust's core contribution: TraceRank.
    Formula:
        w_i = d_t * exp(-lambda * age_days) * rater_trust
        score_raw = sum(quality_i * w_i) / sum(w_i)
        consistency_penalty = 1.0 - consistency_weight * std_dev(quality_i)
        score_a = score_raw * consistency_penalty
    Rater trust incorporates stake via sublinear scaling:
        stake_weight = log(1 + stake)
    and propagates over iterations to suppress Sybils without stake.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("tracerank", config)
        self.lambda_decay = float(self.config.get("lambda_decay", 0.1))
        self.difficulty_min = float(self.config.get("difficulty_min", 0.1))
        self.difficulty_max = float(self.config.get("difficulty_max", 1.0))
        self.consistency_weight = float(self.config.get("consistency_weight", 0.3))
        self.stake_fn = str(self.config.get("stake_fn", "log1p"))
        self.propagation_iter = int(self.config.get("propagation_iterations", 20))
        self.tol = float(self.config.get("convergence_tol", 1e-6))

    def _scale_stake(self, stake: float) -> float:
        s = max(0.0, float(stake))
        if self.stake_fn == "log1p":
            return math.log1p(s)
        elif self.stake_fn == "sqrt":
            return math.sqrt(s)
        elif self.stake_fn == "linear":
            return s
        return math.log1p(s)

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        agent_list = list(agents)
        agent_ids = [getattr(ag, "agent_id", None) or ag.get("agent_id") for ag in agent_list]
        if not agent_ids:
            return {}

        now = reference_time or datetime.now(timezone.utc)
        diff_map = task_difficulties or compute_task_difficulties(
            interactions, d_min=self.difficulty_min, d_max=self.difficulty_max
        )

        # 1. Base rater trust initialized from stake
        rater_trust: Dict[str, float] = {}
        for ag in agent_list:
            aid = getattr(ag, "agent_id", None) or ag.get("agent_id")
            stake = getattr(ag, "stake", 0) or (ag.get("stake", 0) if isinstance(ag, dict) else 0)
            scaled_stake = self._scale_stake(stake)
            # Baseline minimum trust 1.0 + sublinear stake
            rater_trust[aid] = 1.0 + scaled_stake

        # Normalize rater trust sum to number of agents
        total_rt = sum(rater_trust.values())
        if total_rt > 0:
            scale = len(agent_ids) / total_rt
            for aid in agent_ids:
                rater_trust[aid] *= scale

        # 2. Iterative propagation of rater trust
        # Group interactions by agent
        agent_inters: Dict[str, List[Any]] = {aid: [] for aid in agent_ids}
        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            if aid in agent_inters:
                agent_inters[aid].append(inter)

        current_scores = {aid: 0.5 for aid in agent_ids}

        for _ in range(self.propagation_iter):
            new_scores: Dict[str, float] = {}
            for aid in agent_ids:
                inters = agent_inters[aid]
                if not inters:
                    new_scores[aid] = 0.0
                    continue

                w_sum = 0.0
                weighted_q = 0.0
                q_vals: List[float] = []

                for inter in inters:
                    tid = getattr(inter, "task_id", None) or inter.get("task_id")
                    q = float(getattr(inter, "quality_score", None) if getattr(inter, "quality_score", None) is not None else (inter.get("quality_score", 0.0) if isinstance(inter, dict) else 0.0))
                    q_vals.append(q)

                    ts = getattr(inter, "timestamp", None) or (inter.get("timestamp") if isinstance(inter, dict) else None)
                    if ts is None:
                        age_days = 0.0
                    else:
                        if isinstance(ts, str):
                            try:
                                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            except Exception:
                                ts = None
                        if ts is None:
                            age_days = 0.0
                        else:
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            age_days = max(0.0, (now - ts).total_seconds() / 86400.0)

                    d_t = diff_map.get(tid, 0.5)
                    decay = math.exp(-self.lambda_decay * age_days)
                    # Trust factor based on agent's rater_trust
                    w_i = d_t * decay * rater_trust.get(aid, 1.0)

                    weighted_q += q * w_i
                    w_sum += w_i

                if w_sum > 0:
                    raw_score = weighted_q / w_sum
                else:
                    raw_score = 0.0

                # Consistency multiplier: lower variance -> higher multiplier
                std_dev = float(np.std(q_vals)) if len(q_vals) > 1 else 0.0
                consistency_mult = max(0.0, 1.0 - (self.consistency_weight * std_dev))

                new_scores[aid] = float(np.clip(raw_score * consistency_mult, 0.0, 1.0))

            # Update rater trust based on performance and stake
            diff = max(abs(new_scores[a] - current_scores[a]) for a in agent_ids)
            current_scores = new_scores
            if diff < self.tol:
                break

            # Update rater trust with feedback
            for aid in agent_ids:
                stake = getattr(ag, "stake", 0) if (ag := next((x for x in agent_list if (getattr(x, "agent_id", None) or x.get("agent_id")) == aid), None)) else 0
                stake_val = getattr(stake, "stake", stake) if hasattr(stake, "stake") else stake
                base = 1.0 + self._scale_stake(stake_val if isinstance(stake_val, (int, float)) else 0)
                rater_trust[aid] = base * (0.5 + 0.5 * current_scores[aid])

            tot = sum(rater_trust.values())
            if tot > 0:
                s = len(agent_ids) / tot
                for aid in agent_ids:
                    rater_trust[aid] *= s

        return current_scores


class EloScorer(BaseReputation):
    """
    Computes pairwise Elo tournament ratings across shared benchmark tasks.
    Pairwise outcomes update agent ratings with K-factor=32, normalized to [0, 1].
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("elo", config)
        self.k_factor = float(self.config.get("k_factor", 32.0))
        self.base_rating = float(self.config.get("base_rating", 1500.0))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        agent_ids = sorted([getattr(ag, "agent_id", None) or ag.get("agent_id") for ag in agents])
        if not agent_ids:
            return {}

        ratings: Dict[str, float] = {aid: self.base_rating for aid in agent_ids}

        # Group interactions by task: task_performances[task_id][agent_id] = quality
        task_performances: Dict[str, Dict[str, float]] = {}
        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            tid = getattr(inter, "task_id", None) or inter.get("task_id")
            q = float(getattr(inter, "quality_score", None) if getattr(inter, "quality_score", None) is not None else (inter.get("quality_score", 0.0) if isinstance(inter, dict) else 0.0))
            if tid not in task_performances:
                task_performances[tid] = {}
            # Take max quality if multiple attempts
            task_performances[tid][aid] = max(task_performances[tid].get(aid, 0.0), q)

        # Process pairwise matches deterministically
        for tid in sorted(task_performances.keys()):
            perf = task_performances[tid]
            contenders = sorted([aid for aid in perf.keys() if aid in ratings])
            for i in range(len(contenders)):
                for j in range(i + 1, len(contenders)):
                    a = contenders[i]
                    b = contenders[j]
                    qa = perf[a]
                    qb = perf[b]

                    if qa > qb:
                        sa, sb = 1.0, 0.0
                    elif qa < qb:
                        sa, sb = 0.0, 1.0
                    else:
                        sa, sb = 0.5, 0.5

                    ra = ratings[a]
                    rb = ratings[b]
                    ea = 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))
                    eb = 1.0 / (1.0 + 10.0 ** ((ra - rb) / 400.0))

                    ratings[a] += self.k_factor * (sa - ea)
                    ratings[b] += self.k_factor * (sb - eb)

        # Min-max scale to [0, 1]
        vals = [ratings[aid] for aid in agent_ids]
        min_r = min(vals) if vals else self.base_rating
        max_r = max(vals) if vals else self.base_rating

        results: Dict[str, float] = {}
        if max_r > min_r:
            for aid in agent_ids:
                results[aid] = float((ratings[aid] - min_r) / (max_r - min_r))
        else:
            for aid in agent_ids:
                results[aid] = 0.5
        return results


class BetaReputationScorer(BaseReputation):
    """
    Computes reputation using a Bayesian Beta distribution model Beta(alpha, beta).
    Prior: alpha=1.0, beta=1.0.
    For each interaction, alpha += q, beta += (1 - q).
    Expected value score = alpha / (alpha + beta) in [0, 1].
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("beta", config)
        self.prior_alpha = float(self.config.get("prior_alpha", 1.0))
        self.prior_beta = float(self.config.get("prior_beta", 1.0))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        agent_ids = sorted([getattr(ag, "agent_id", None) or ag.get("agent_id") for ag in agents])
        if not agent_ids:
            return {}

        alphas = {aid: self.prior_alpha for aid in agent_ids}
        betas = {aid: self.prior_beta for aid in agent_ids}

        for inter in interactions:
            aid = getattr(inter, "agent_id", None) or inter.get("agent_id")
            if aid not in alphas:
                continue
            q = float(getattr(inter, "quality_score", None) if getattr(inter, "quality_score", None) is not None else (inter.get("quality_score", 0.0) if isinstance(inter, dict) else 0.0))
            q_clamped = max(0.0, min(1.0, q))
            alphas[aid] += q_clamped
            betas[aid] += (1.0 - q_clamped)

        return {
            aid: float(alphas[aid] / (alphas[aid] + betas[aid]))
            for aid in agent_ids
        }


def get_scorer(method: str, config: Optional[Dict[str, Any]] = None) -> BaseReputation:
    """Factory function returning the scoring algorithm by name."""
    m = method.lower()
    if m in ("simple_avg", "mean"):
        return SimpleAverage(config)
    elif m == "weighted":
        return WeightedHistory(config)
    elif m == "pagerank":
        return PageRankScorer(config)
    elif m == "eigentrust":
        return EigenTrustScorer(config)
    elif m == "tracerank":
        return TraceRankScorer(config)
    elif m == "elo":
        return EloScorer(config)
    elif m == "beta":
        return BetaReputationScorer(config)
    elif m == "chs":
        from chaintrust.reputation.chs import CHSScorer
        return CHSScorer(config)
    else:
        raise ValueError(f"Unknown reputation scoring method: {method!r}")
