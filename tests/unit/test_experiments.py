"""
tests/unit/test_experiments.py
Unit tests for SybilSimulator and experiment runner.
"""

import pytest

from chaintrust.experiments.runner import run_sybil_experiments
from chaintrust.experiments.sybil_simulator import SybilSimulator


class TestSybilSimulator:
    def test_synthetic_honest_population(self):
        sim = SybilSimulator(top_k=3)
        agents, inters = sim.create_synthetic_honest_population(num_honest=4, tasks_per_agent=5)
        assert len(agents) == 4
        assert len(inters) == 20
        assert all("agent_id" in a for a in agents)
        assert all("quality_score" in i for i in inters)

    def test_inject_sybil_clones(self):
        sim = SybilSimulator(top_k=2)
        honest_agents, honest_inters = sim.create_synthetic_honest_population(num_honest=3, tasks_per_agent=4)
        all_agents, all_inters = sim.inject_sybil_clones(honest_agents, honest_inters, num_clones=5)
        assert len(all_agents) == 3 + 5
        assert len(all_inters) > len(honest_inters)
        # Check sybils have 0 stake
        sybils = [a for a in all_agents if a["agent_id"].startswith("sybil_")]
        assert len(sybils) == 5
        assert all(s["stake"] == 0 for s in sybils)

    def test_evaluate_resilience(self):
        sim = SybilSimulator(top_k=2, methods=["simple_avg", "tracerank"])
        honest_agents, honest_inters = sim.create_synthetic_honest_population(num_honest=4, tasks_per_agent=6)
        results = sim.evaluate_resilience(
            honest_agents=honest_agents,
            honest_interactions=honest_inters,
            clone_counts=[0, 3],
        )
        assert len(results) == 2
        for r in results:
            assert "tracerank" in r.algorithm_metrics
            assert "simple_avg" in r.algorithm_metrics
            assert "kendall_tau" in r.algorithm_metrics["tracerank"]

    def test_run_experiments_writes_files(self, tmp_path):
        cfg = {
            "experiments": {
                "output_dir": str(tmp_path),
                "sybil_clone_counts": [0, 2],
                "top_k": 2,
            }
        }
        results = run_sybil_experiments(cfg)
        assert len(results) == 2
        assert (tmp_path / "sybil_resilience.json").exists()
        assert (tmp_path / "sybil_resilience.csv").exists()
