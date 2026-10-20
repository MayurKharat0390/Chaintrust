"""
tests/unit/test_experiments_suite.py
Tests for the Phase 5 empirical and adversarial experiment suite:
Validates that Experiments A through F run reproducibly and produce valid CSV and PNG artifacts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chaintrust.experiments.suite import (
    run_experiment_a,
    run_experiment_b,
    run_experiment_c,
    run_experiment_d,
    run_experiment_e,
    run_experiment_f,
)


def test_experiment_a_validity(tmp_path: Path):
    """Experiment A generates validity correlations and saves CSV + PNG."""
    df = run_experiment_a(output_dir=tmp_path)
    assert not df.empty
    assert "method" in df.columns
    assert "spearman_rho" in df.columns
    assert "kendall_tau" in df.columns
    assert (tmp_path / "experiment_a_validity.csv").exists()
    assert (tmp_path / "experiment_a_validity.png").exists()


def test_experiment_b_sybil_clones(tmp_path: Path):
    """Experiment B evaluates Sybil clone resistance with K=0, 5."""
    df = run_experiment_b(output_dir=tmp_path, clone_counts=(0, 5), seed=42)
    assert not df.empty
    assert "clone_count" in df.columns
    assert "best_attacker_rank" in df.columns
    assert "score_inflation_pct" in df.columns
    assert (tmp_path / "experiment_b_sybil_clones.csv").exists()
    assert (tmp_path / "experiment_b_sybil_clones.png").exists()


def test_experiment_c_collusion_ring(tmp_path: Path):
    """Experiment C evaluates collusion ring resilience."""
    df = run_experiment_c(output_dir=tmp_path, seed=42)
    assert not df.empty
    assert "ring_inflation_pct" in df.columns
    assert "honest_top_k_preserved" in df.columns
    assert (tmp_path / "experiment_c_collusion_ring.csv").exists()
    assert (tmp_path / "experiment_c_collusion_ring.png").exists()


def test_experiment_d_ablations(tmp_path: Path):
    """Experiment D runs CHS component ablations."""
    df = run_experiment_d(output_dir=tmp_path, seed=42)
    assert len(df) >= 5
    assert "ablation" in df.columns
    assert "collusion_advantage" in df.columns
    assert (tmp_path / "experiment_d_ablations.csv").exists()
    assert (tmp_path / "experiment_d_ablations.png").exists()


def test_experiment_e_sensitivity(tmp_path: Path):
    """Experiment E runs hyperparameter sensitivity sweeps."""
    df = run_experiment_e(output_dir=tmp_path)
    assert not df.empty
    assert "parameter" in df.columns
    assert "value" in df.columns
    assert (tmp_path / "experiment_e_sensitivity.csv").exists()
    assert (tmp_path / "experiment_e_sensitivity.png").exists()


def test_experiment_f_tamper_detection(tmp_path: Path):
    """Experiment F verifies 100% cryptographic tamper detection."""
    summary = run_experiment_f(output_dir=tmp_path, trials_per_type=5, seed=42)
    assert not summary.empty
    assert "detection_rate_pct" in summary.columns
    # Check that all trials detected tampering
    assert (summary["detection_rate_pct"] == 100.0).all()
    assert (tmp_path / "experiment_f_tamper_detection.csv").exists()
    assert (tmp_path / "experiment_f_tamper_detection.png").exists()
