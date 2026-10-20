"""
chaintrust/reputation/engine.py
Reputation engine orchestrating task difficulty updates, multi-method reputation scoring,
epoch management, and database persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from chaintrust.config import get_config
from chaintrust.db.models import Agent, Interaction, Reputation, Task
from chaintrust.db.session import get_session
from chaintrust.reputation.algorithms import (
    BaseReputation,
    compute_task_difficulties,
    get_scorer,
)

logger = logging.getLogger("chaintrust.reputation")


class ReputationEngine:
    """
    Coordinates reputation score calculation across configured algorithms.
    """

    SUPPORTED_METHODS = [
        "simple_avg",
        "weighted",
        "pagerank",
        "eigentrust",
        "tracerank",
        "chs",
        "elo",
        "beta",
    ]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or get_config()
        self.rep_config = self.config.get("reputation", {})
        self.rounding_decimals = int(self.rep_config.get("rounding_decimals", 6))
        self.epoch_size = int(self.rep_config.get("epoch_size", 50))

    def update_task_difficulties(self, session: Session) -> Dict[str, float]:
        """
        Computes dynamic difficulty d_t for each task and persists to DB.
        """
        interactions = session.query(Interaction).all()
        tracerank_cfg = self.rep_config.get("tracerank", {})
        d_min = float(tracerank_cfg.get("difficulty_min", 0.1))
        d_max = float(tracerank_cfg.get("difficulty_max", 1.0))
        smoothing = float(tracerank_cfg.get("difficulty_smoothing", 1.0))

        diff_map = compute_task_difficulties(
            interactions, d_min=d_min, d_max=d_max, smoothing=smoothing
        )

        for tid, diff in diff_map.items():
            task = session.get(Task, tid)
            if task:
                task.difficulty_weight = round(diff, self.rounding_decimals)

        # Snapshot difficulty weight on interactions that don't have it yet
        for inter in interactions:
            if inter.difficulty_weight is None and inter.task_id in diff_map:
                inter.difficulty_weight = round(diff_map[inter.task_id], self.rounding_decimals)

        session.commit()
        return diff_map

    def compute_epoch_scores(
        self,
        session: Session,
        epoch: int,
        methods: Optional[Sequence[str]] = None,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Computes reputation scores for all agents for a specific epoch across methods.
        Returns:
            dict: {method_name: {agent_id: score}}
        """
        selected_methods = list(methods or self.SUPPORTED_METHODS)
        agents = session.query(Agent).all()
        interactions = session.query(Interaction).all()

        if not agents or not interactions:
            logger.warning("No agents or interactions found in database.")
            return {m: {} for m in selected_methods}

        # Update difficulty weights
        diff_map = self.update_task_difficulties(session)

        now = reference_time or datetime.now(timezone.utc)
        all_results: Dict[str, Dict[str, float]] = {}

        for method in selected_methods:
            method_cfg = self.rep_config.get(method, {})
            scorer = get_scorer(method, method_cfg)
            scores = scorer.compute(
                interactions=interactions,
                agents=agents,
                task_difficulties=diff_map,
                reference_time=now,
            )

            # Round scores
            rounded = {
                aid: round(float(score), self.rounding_decimals)
                for aid, score in scores.items()
            }
            all_results[method] = rounded

            # Check if method has a params_hash
            params_hash = None
            if method.lower() == "chs":
                from chaintrust.reputation.chs import load_chs_params
                _, params_hash = load_chs_params()

            # Save to Reputation table
            for aid, score in rounded.items():
                existing = (
                    session.query(Reputation)
                    .filter_by(agent_id=aid, epoch=epoch, method=method)
                    .first()
                )
                if existing:
                    existing.score = score
                    if params_hash:
                        existing.params_hash = params_hash
                    existing.computed_at = now
                else:
                    rep_row = Reputation(
                        agent_id=aid,
                        epoch=epoch,
                        method=method,
                        score=score,
                        params_hash=params_hash,
                        computed_at=now,
                    )
                    session.add(rep_row)

        session.commit()
        return all_results

    def compute_latest(
        self, session: Optional[Session] = None, epoch: Optional[int] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Convenience method to compute scores using current interactions count as epoch basis.
        """
        if session is not None:
            total_interactions = session.query(Interaction).count()
            current_epoch = epoch if epoch is not None else max(1, (total_interactions // self.epoch_size) + 1)
            return self.compute_epoch_scores(session, epoch=current_epoch)
        else:
            with get_session() as sess:
                total_interactions = sess.query(Interaction).count()
                current_epoch = epoch if epoch is not None else max(1, (total_interactions // self.epoch_size) + 1)
                return self.compute_epoch_scores(sess, epoch=current_epoch)
