"""
chaintrust/reputation/chs.py
ChainTrust Hybrid Score (CHS) Algorithm Implementation.

Implements the multi-layer hybrid reputation algorithm:
- Step 1: Task difficulty d_t with family-level deduplication
- Step 2: Direct evidence score D'_a with empirical Bayes shrinkage and consistency C_a
- Step 3: Trust propagation T~_a with capped stake factor and clone-split seeds
- Step 4: Defense penalty pi_a targeting mutual collusion rings and rater concentration
- Step 5: Final composite score CHS_a

Deterministic, reproducible, and mathematically rigorous.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

from chaintrust.reputation.algorithms import BaseReputation


@dataclass(frozen=True)
class CHSParams:
    """Versioned parameter set for CHS algorithm."""
    version: str = "1.0.0"
    decay_lambda: float = 0.023104906018664842  # ln(2)/30
    alpha0: float = 2.0                          # Prior strength for task difficulty
    d_min: float = 0.1                           # Minimum task difficulty floor
    m: float = 5.0                               # Empirical Bayes shrinkage strength
    beta: float = 0.85                           # Propagation damping factor
    S_cap: float = 1000.0                        # Stake ceiling for rater weight
    w: float = 0.3                               # Weight of trust layer
    omega: float = 0.5                           # Consistency exponent
    kappa1: float = 0.5                          # Defense mutual rating penalty weight
    kappa2: float = 0.3                          # Defense rater concentration penalty weight
    pi_max: float = 0.8                          # Maximum defense penalty cap
    N_iter: int = 50                             # Fixed power iterations count

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def canonical_json_str(data: Any) -> str:
    """Deterministic JSON string with sorted keys and normalized floats."""
    def _default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, float):
            return round(o, 9)
        return str(o)

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)


def compute_params_hash(params: CHSParams | Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of canonical JSON params."""
    data = asdict(params) if isinstance(params, CHSParams) else dict(params)
    payload = canonical_json_str(data).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_chs_params(config_path: Optional[str | Path] = None) -> Tuple[CHSParams, str]:
    """
    Load CHSParams from config/chs_params.yaml and compute params_hash.
    If path is None, looks for config/chs_params.yaml in repo root.
    """
    if config_path is None:
        # Search relative to this file or cwd
        candidates = [
            Path("config/chs_params.yaml"),
            Path(__file__).resolve().parent.parent.parent / "config" / "chs_params.yaml",
        ]
        chosen = next((c for c in candidates if c.exists()), None)
    else:
        chosen = Path(config_path)

    if chosen and chosen.exists():
        with open(chosen, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    params = CHSParams(
        version=str(raw.get("version", "1.0.0")),
        decay_lambda=float(raw.get("lambda", raw.get("decay_lambda", math.log(2.0) / 30.0))),
        alpha0=float(raw.get("alpha0", 2.0)),
        d_min=float(raw.get("d_min", 0.1)),
        m=float(raw.get("m", 5.0)),
        beta=float(raw.get("beta", 0.85)),
        S_cap=float(raw.get("S_cap", 1000.0)),
        w=float(raw.get("w", 0.3)),
        omega=float(raw.get("omega", 0.5)),
        kappa1=float(raw.get("kappa1", 0.5)),
        kappa2=float(raw.get("kappa2", 0.3)),
        pi_max=float(raw.get("pi_max", 0.8)),
        N_iter=int(raw.get("N_iter", 50)),
    )
    p_hash = compute_params_hash(params)
    return params, p_hash


def get_agent_id(agent: Any) -> str:
    """Extract agent_id as string."""
    return str(getattr(agent, "agent_id", None) or (agent.get("agent_id") if isinstance(agent, dict) else agent))


def get_agent_stake(agent: Any) -> float:
    """Extract stake as float."""
    s = getattr(agent, "stake", None)
    if s is None and isinstance(agent, dict):
        s = agent.get("stake", 0)
    try:
        return float(s or 0.0)
    except Exception:
        return 0.0


def get_agent_family(agent: Any) -> Tuple[str, str]:
    """Extract model family (provider, model) tuple."""
    provider = str(getattr(agent, "provider", None) or (agent.get("provider", "unknown") if isinstance(agent, dict) else "unknown"))
    model = str(getattr(agent, "model", None) or (agent.get("model", "unknown") if isinstance(agent, dict) else "unknown"))
    return provider.strip().lower(), model.strip().lower()


def parse_timestamp(ts: Any) -> Optional[datetime]:
    """Parse timestamp into UTC datetime."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Step 1: Task difficulty (one vote per model family)
# ---------------------------------------------------------------------------
def difficulty(
    interactions: Sequence[Any],
    agents: Sequence[Any],
    P: CHSParams,
) -> Dict[str, float]:
    """
    Step 1: Compute task difficulties d_t.
        q_ft = mean quality of family f on task t
        p_t  = ( sum_f q_ft + alpha0 * 0.5 ) / ( F_t + alpha0 )
        d_t  = clip( 1 - p_t, d_min, 1 )
    Deterministic sorting by task ID; rounded to 9 decimals.
    """
    # Build agent_id -> family map
    agent_family_map: Dict[str, Tuple[str, str]] = {}
    for ag in agents:
        aid = get_agent_id(ag)
        agent_family_map[aid] = get_agent_family(ag)

    # Group attempts by task_id and family
    task_family_scores: Dict[str, Dict[Tuple[str, str], List[float]]] = {}
    for inter in interactions:
        aid = str(getattr(inter, "agent_id", None) or inter.get("agent_id"))
        tid = str(getattr(inter, "task_id", None) or inter.get("task_id"))
        q = getattr(inter, "quality_score", None)
        if q is None and isinstance(inter, dict):
            q = inter.get("quality_score", inter.get("quality", 0.0))
        q_val = float(q if q is not None else 0.0)

        fam = agent_family_map.get(aid, ("unknown", "unknown"))
        if tid not in task_family_scores:
            task_family_scores[tid] = {}
        if fam not in task_family_scores[tid]:
            task_family_scores[tid][fam] = []
        task_family_scores[tid][fam].append(q_val)

    difficulties: Dict[str, float] = {}
    for tid in sorted(task_family_scores.keys()):
        fam_dict = task_family_scores[tid]
        fam_means = [float(np.mean(q_list)) for fam, q_list in sorted(fam_dict.items())]
        F_t = len(fam_means)

        if F_t > 0:
            p_t = (sum(fam_means) + P.alpha0 * 0.5) / (F_t + P.alpha0)
        else:
            p_t = 0.5

        raw_dt = 1.0 - p_t
        d_t = max(P.d_min, min(1.0, raw_dt))
        difficulties[tid] = round(d_t, 9)

    return difficulties


# ---------------------------------------------------------------------------
# Step 2: Direct evidence score
# ---------------------------------------------------------------------------
def direct_scores(
    interactions: Sequence[Any],
    d: Dict[str, float],
    P: CHSParams,
    as_of: datetime,
    agents: Optional[Sequence[Any]] = None,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """
    Step 2: Compute direct evidence score D'_a, effective attempt weight n_a, and consistency C_a.
        s_at     = mean quality of agent a over its attempts on task t
        delta_at = exp( -lambda * age_in_days of a's latest attempt on t )
        n_a      = sum_t d_t * delta_at
        D_a      = sum_t d_t * delta_at * s_at / n_a  (0.0 if n_a == 0)
        D'_a     = ( n_a * D_a + m * mu0 ) / ( n_a + m )
        C_a      = clip( 1 - 2 * mean_t( std of a's attempts on t ), 0, 1 )
    Returns:
        (D_prime, n_a, C_a)
    """
    as_of_utc = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=timezone.utc)

    # Group interactions by (agent_id, task_id)
    # Storing list of (quality, timestamp)
    agent_task_data: Dict[str, Dict[str, List[Tuple[float, datetime]]]] = {}
    all_agent_ids: set[str] = set()

    if agents is not None:
        for ag in agents:
            all_agent_ids.add(get_agent_id(ag))

    for inter in interactions:
        aid = str(getattr(inter, "agent_id", None) or inter.get("agent_id"))
        tid = str(getattr(inter, "task_id", None) or inter.get("task_id"))
        q = getattr(inter, "quality_score", None)
        if q is None and isinstance(inter, dict):
            q = inter.get("quality_score", inter.get("quality", 0.0))
        q_val = float(q if q is not None else 0.0)

        ts = parse_timestamp(getattr(inter, "timestamp", None) or (inter.get("timestamp") if isinstance(inter, dict) else None))
        if ts is None:
            ts = as_of_utc

        all_agent_ids.add(aid)
        if aid not in agent_task_data:
            agent_task_data[aid] = {}
        if tid not in agent_task_data[aid]:
            agent_task_data[aid][tid] = []
        agent_task_data[aid][tid].append((q_val, ts))

    n_a_raw: Dict[str, float] = {}
    D_a_raw: Dict[str, float] = {}
    C_a_raw: Dict[str, float] = {}

    for aid in sorted(all_agent_ids):
        tasks_map = agent_task_data.get(aid, {})
        weighted_q_sum = 0.0
        n_a_val = 0.0
        task_stds: List[float] = []

        for tid in sorted(tasks_map.keys()):
            attempts = tasks_map[tid]
            q_list = [item[0] for item in attempts]
            ts_list = [item[1] for item in attempts]

            # Mean quality over attempts for task t
            s_at = float(np.mean(q_list))

            # Age of latest attempt on task t
            latest_ts = max(ts_list)
            age_days = max(0.0, (as_of_utc - latest_ts).total_seconds() / 86400.0)
            delta_at = math.exp(-P.decay_lambda * age_days)

            d_t = d.get(tid, 0.5)
            weight = d_t * delta_at

            weighted_q_sum += weight * s_at
            n_a_val += weight

            # Population std (ddof=0); 0.0 if only 1 attempt
            if len(q_list) > 1:
                t_std = float(np.std(q_list, ddof=0))
            else:
                t_std = 0.0
            task_stds.append(t_std)

        n_a_raw[aid] = round(n_a_val, 9)
        if n_a_val > 0.0:
            D_a_raw[aid] = round(weighted_q_sum / n_a_val, 9)
        else:
            D_a_raw[aid] = 0.0

        if task_stds:
            mean_std = float(np.mean(task_stds))
            C_a_val = max(0.0, min(1.0, 1.0 - 2.0 * mean_std))
        else:
            C_a_val = 1.0
        C_a_raw[aid] = round(C_a_val, 9)

    # Compute global mean mu0 over agents with n_a > 0
    active_d_vals = [D_a_raw[aid] for aid in sorted(all_agent_ids) if n_a_raw[aid] > 0.0]
    if active_d_vals:
        mu0 = round(float(np.mean(active_d_vals)), 9)
    else:
        mu0 = 0.5

    D_prime: Dict[str, float] = {}
    for aid in sorted(all_agent_ids):
        na = n_a_raw[aid]
        da = D_a_raw[aid]
        d_prime_val = (na * da + P.m * mu0) / (na + P.m)
        D_prime[aid] = round(d_prime_val, 9)

    return D_prime, n_a_raw, C_a_raw


# ---------------------------------------------------------------------------
# Step 3: Trust propagation (only if peer ratings exist)
# ---------------------------------------------------------------------------
def propagate(
    D_prime: Dict[str, float],
    n_a: Dict[str, float],
    agents: Sequence[Any],
    ratings: Optional[Sequence[Any]],
    P: CHSParams,
) -> Dict[str, float]:
    """
    Step 3: Trust propagation across peer-rating graph.
        M_ba      = r_ba / sum_x r_bx  (row-normalized)
        g_b       = min( 1, log(1 + S_b) / log(1 + S_cap) )
        seed p_a  = ( D'_a / n_family(a) ) / sum_x ( D'_x / n_family(x) )
        T^(0)     = p
        T^(k+1)_a = (1 - beta) * p_a + beta * sum_b T^(k)_b * g_b * M_ba
        T~_a      = T_a / max(T)
    If ratings is None or empty:
        T~_a = D'_a
    """
    sorted_agent_ids = sorted([get_agent_id(ag) for ag in agents])
    if not sorted_agent_ids:
        return {}

    # If no ratings provided, CHS reduces to Layer 1 (T~_a = D'_a)
    if not ratings:
        return {aid: round(D_prime.get(aid, 0.0), 9) for aid in sorted_agent_ids}

    # Count agents per family
    family_counts: Dict[Tuple[str, str], int] = {}
    agent_family_map: Dict[str, Tuple[str, str]] = {}
    agent_stake_map: Dict[str, float] = {}

    for ag in agents:
        aid = get_agent_id(ag)
        fam = get_agent_family(ag)
        agent_family_map[aid] = fam
        agent_stake_map[aid] = get_agent_stake(ag)
        family_counts[fam] = family_counts.get(fam, 0) + 1

    # Stake factor g_b for each agent
    log_scap = math.log1p(P.S_cap) if P.S_cap > 0 else 1.0
    g: Dict[str, float] = {}
    for aid in sorted_agent_ids:
        s_b = agent_stake_map.get(aid, 0.0)
        if s_b > 0 and log_scap > 0:
            g_b = min(1.0, math.log1p(s_b) / log_scap)
        else:
            g_b = 0.0
        g[aid] = round(g_b, 9)

    # Seed vector p_a: splits seed among clones in the same family
    unnormalized_p: Dict[str, float] = {}
    for aid in sorted_agent_ids:
        fam = agent_family_map.get(aid, ("unknown", "unknown"))
        n_fam = family_counts.get(fam, 1)
        d_p = D_prime.get(aid, 0.0)
        unnormalized_p[aid] = d_p / max(1, n_fam)

    sum_unnorm = sum(unnormalized_p.values())
    p: Dict[str, float] = {}
    for aid in sorted_agent_ids:
        if sum_unnorm > 0:
            p[aid] = round(unnormalized_p[aid] / sum_unnorm, 9)
        else:
            p[aid] = round(1.0 / len(sorted_agent_ids), 9)

    # Build rating matrix M_ba: row is rater b, column is ratee a
    # Rating extraction handles dicts or ORM rows
    ratings_raw: Dict[str, Dict[str, float]] = {aid: {} for aid in sorted_agent_ids}
    for r in ratings:
        b = str(getattr(r, "rater_id", None) or (r.get("rater_id", r.get("from_agent")) if isinstance(r, dict) else None))
        a = str(getattr(r, "ratee_id", None) or (r.get("ratee_id", r.get("to_agent")) if isinstance(r, dict) else None))
        val = getattr(r, "rating", None)
        if val is None and isinstance(r, dict):
            val = r.get("rating", 0.0)
        val_f = float(val if val is not None else 0.0)

        if b in ratings_raw and a in sorted_agent_ids:
            # If multiple ratings from b to a, take average
            ratings_raw[b][a] = val_f

    # Row-normalize M
    M: Dict[str, Dict[str, float]] = {b: {} for b in sorted_agent_ids}
    for b in sorted_agent_ids:
        row = ratings_raw[b]
        row_sum = sum(row.values())
        for a in sorted_agent_ids:
            if row_sum > 0 and a in row:
                M[b][a] = round(row[a] / row_sum, 9)
            else:
                M[b][a] = 0.0

    # Iterative trust propagation for exactly N_iter iterations
    T = {aid: p[aid] for aid in sorted_agent_ids}

    for _ in range(P.N_iter):
        T_next: Dict[str, float] = {}
        for a in sorted_agent_ids:
            # sum_b T_b * g_b * M_ba
            propagated_sum = sum(T[b] * g[b] * M[b].get(a, 0.0) for b in sorted_agent_ids)
            t_val = (1.0 - P.beta) * p[a] + P.beta * propagated_sum
            T_next[a] = round(t_val, 9)
        T = T_next

    # Max-scale T~_a = T_a / max(T)
    max_T = max(T.values()) if T else 0.0
    T_tilde: Dict[str, float] = {}
    for aid in sorted_agent_ids:
        if max_T > 0:
            T_tilde[aid] = round(T[aid] / max_T, 9)
        else:
            T_tilde[aid] = 0.0

    return T_tilde


# ---------------------------------------------------------------------------
# Step 4: Defense penalty
# ---------------------------------------------------------------------------
def defense(
    ratings: Optional[Sequence[Any]],
    agents: Sequence[Any],
    P: CHSParams,
) -> Dict[str, float]:
    """
    Step 4: Collusion defense penalty.
        m_a = share of a's incoming rating weight coming from raters that a also rates >= 0.5 (mutual)
        H_a = sum_b ( share of a's incoming weight from b )^2
        pi_a = min( pi_max, kappa1 * m_a + kappa2 * H_a )
    If no ratings exist, pi_a = 0.0.
    """
    sorted_agent_ids = sorted([get_agent_id(ag) for ag in agents])
    if not sorted_agent_ids or not ratings:
        return {aid: 0.0 for aid in sorted_agent_ids}

    # Extract directed ratings map: ratings_map[b][a] = r_ba
    ratings_map: Dict[str, Dict[str, float]] = {aid: {} for aid in sorted_agent_ids}
    for r in ratings:
        b = str(getattr(r, "rater_id", None) or (r.get("rater_id", r.get("from_agent")) if isinstance(r, dict) else None))
        a = str(getattr(r, "ratee_id", None) or (r.get("ratee_id", r.get("to_agent")) if isinstance(r, dict) else None))
        val = getattr(r, "rating", None)
        if val is None and isinstance(r, dict):
            val = r.get("rating", 0.0)
        val_f = float(val if val is not None else 0.0)

        if b in ratings_map and a in sorted_agent_ids:
            ratings_map[b][a] = val_f

    pi: Dict[str, float] = {}
    for a in sorted_agent_ids:
        # Incoming ratings to a from each b
        incoming_from_b: Dict[str, float] = {}
        for b in sorted_agent_ids:
            if a in ratings_map[b] and ratings_map[b][a] > 0.0:
                incoming_from_b[b] = ratings_map[b][a]

        total_incoming = sum(incoming_from_b.values())
        if total_incoming <= 0.0:
            pi[a] = 0.0
            continue

        # Mutual incoming share: b where r_ab >= 0.5
        mutual_incoming = 0.0
        herfindahl = 0.0
        for b, r_ba in incoming_from_b.items():
            share = r_ba / total_incoming
            herfindahl += share * share
            # Check if a also rates b >= 0.5
            r_ab = ratings_map[a].get(b, 0.0)
            if r_ab >= 0.5:
                mutual_incoming += r_ba

        m_a = mutual_incoming / total_incoming
        H_a = herfindahl

        penalty = min(P.pi_max, P.kappa1 * m_a + P.kappa2 * H_a)
        pi[a] = round(penalty, 9)

    return pi


# ---------------------------------------------------------------------------
# Step 5: Final CHS Composite Score
# ---------------------------------------------------------------------------
def chs(
    interactions: Sequence[Any],
    agents: Sequence[Any],
    ratings: Optional[Sequence[Any]],
    P: CHSParams,
    as_of: datetime,
) -> Dict[str, float]:
    """
    Step 5: Compute full ChainTrust Hybrid Score (CHS).
        CHS_a = round( C_a^omega * [ (1 - w) * D'_a + w * T~_a ] * (1 - pi_a), 6 )
    """
    sorted_agents = sorted(agents, key=get_agent_id)
    sorted_agent_ids = [get_agent_id(ag) for ag in sorted_agents]
    if not sorted_agent_ids:
        return {}

    # Step 1: Difficulty
    d = difficulty(interactions, sorted_agents, P)

    # Step 2: Direct evidence
    D_prime, n_a, C_a = direct_scores(interactions, d, P, as_of, agents=sorted_agents)

    # Step 3: Propagation
    if ratings is None or len(ratings) == 0:
        T_tilde = {aid: D_prime.get(aid, 0.0) for aid in sorted_agent_ids}
        pi = {aid: 0.0 for aid in sorted_agent_ids}
    else:
        T_tilde = propagate(D_prime, n_a, sorted_agents, ratings, P)
        pi = defense(ratings, sorted_agents, P)

    # Step 5: Composite score rounded to 6 decimals
    final_scores: Dict[str, float] = {}
    for aid in sorted_agent_ids:
        c_val = C_a.get(aid, 1.0)
        d_prime_val = D_prime.get(aid, 0.0)
        t_tilde_val = T_tilde.get(aid, 0.0)
        pi_val = pi.get(aid, 0.0)

        # C_a^omega
        c_factor = math.pow(max(0.0, c_val), P.omega)
        # (1 - w) * D'_a + w * T~_a
        core_trust = (1.0 - P.w) * d_prime_val + P.w * t_tilde_val
        # (1 - pi_a)
        defense_factor = max(0.0, 1.0 - pi_val)

        raw_score = c_factor * core_trust * defense_factor
        final_scores[aid] = round(raw_score, 6)

    return final_scores


def chs_breakdown(
    interactions: Sequence[Any],
    agents: Sequence[Any],
    ratings: Optional[Sequence[Any]] = None,
    P: Optional[CHSParams] = None,
    as_of: Optional[datetime] = None,
) -> Tuple[Dict[str, Dict[str, float]], str]:
    """
    Compute CHS with detailed intermediate component breakdown:
    D'_a, C_a, T~_a, pi_a, and final CHS_a score.
    Returns (breakdown_dict, params_hash).
    """
    if P is None:
        P, p_hash = load_chs_params()
    else:
        p_hash = compute_params_hash(P)

    ref_time = as_of or datetime.now(timezone.utc)
    sorted_agents = sorted(agents, key=get_agent_id)
    sorted_agent_ids = [get_agent_id(ag) for ag in sorted_agents]
    if not sorted_agent_ids:
        return {}, p_hash

    # Step 1: Difficulty
    d = difficulty(interactions, sorted_agents, P)

    # Step 2: Direct evidence
    D_prime, n_a, C_a = direct_scores(interactions, d, P, ref_time, agents=sorted_agents)

    # Step 3: Propagation
    if ratings is None or len(ratings) == 0:
        T_tilde = {aid: D_prime.get(aid, 0.0) for aid in sorted_agent_ids}
        pi = {aid: 0.0 for aid in sorted_agent_ids}
    else:
        T_tilde = propagate(D_prime, n_a, sorted_agents, ratings, P)
        pi = defense(ratings, sorted_agents, P)

    breakdown: Dict[str, Dict[str, float]] = {}
    for aid in sorted_agent_ids:
        c_val = C_a.get(aid, 1.0)
        d_prime_val = D_prime.get(aid, 0.0)
        t_tilde_val = T_tilde.get(aid, 0.0)
        pi_val = pi.get(aid, 0.0)

        c_factor = math.pow(max(0.0, c_val), P.omega)
        core_trust = (1.0 - P.w) * d_prime_val + P.w * t_tilde_val
        defense_factor = max(0.0, 1.0 - pi_val)
        score = round(c_factor * core_trust * defense_factor, 6)

        breakdown[aid] = {
            "D_prime": round(d_prime_val, 6),
            "C_a": round(c_val, 6),
            "T_tilde": round(t_tilde_val, 6),
            "pi_a": round(pi_val, 6),
            "score": score,
        }

    return breakdown, p_hash


# ---------------------------------------------------------------------------
# BaseReputation Scorer Wrapper (Engine Integration)
# ---------------------------------------------------------------------------
class CHSScorer(BaseReputation):
    """
    ChainTrust Hybrid Score (CHS) Scorer conforming to BaseReputation interface.
    Integrates Step 1-5 with versioned config and params_hash.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("chs", config)
        self.params, self.params_hash = load_chs_params(self.config.get("config_path"))

    def compute(
        self,
        interactions: Sequence[Any],
        agents: Sequence[Any],
        task_difficulties: Optional[Dict[str, float]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, float]:
        as_of = reference_time or datetime.now(timezone.utc)
        ratings = self.config.get("ratings")
        return chs(
            interactions=interactions,
            agents=agents,
            ratings=ratings,
            P=self.params,
            as_of=as_of,
        )
