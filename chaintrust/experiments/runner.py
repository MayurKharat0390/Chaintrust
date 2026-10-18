"""
chaintrust/experiments/runner.py
Experiment orchestrator for running Sybil resilience tests and saving empirical benchmark data.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from chaintrust.config import get_config
from chaintrust.experiments.sybil_simulator import SybilExperimentResult, SybilSimulator

logger = logging.getLogger("chaintrust.experiments")


def run_sybil_experiments(config: Optional[Dict[str, Any]] = None) -> List[SybilExperimentResult]:
    """
    Executes the full Sybil resilience evaluation benchmark and outputs results to disk.
    """
    cfg = config or get_config()
    exp_cfg = cfg.get("experiments", {})
    output_dir = Path(exp_cfg.get("output_dir", "data/experiments"))
    output_dir.mkdir(parents=True, exist_ok=True)

    clone_counts = exp_cfg.get("sybil_clone_counts", [0, 5, 10, 20])
    top_k = int(exp_cfg.get("top_k", 3))

    simulator = SybilSimulator(top_k=top_k)
    honest_agents, honest_inters = simulator.create_synthetic_honest_population()

    results = simulator.evaluate_resilience(
        honest_agents=honest_agents,
        honest_interactions=honest_inters,
        clone_counts=clone_counts,
    )

    # 1. Save JSON
    json_path = output_dir / "sybil_resilience.json"
    json_data = [
        {"clone_count": r.clone_count, "metrics": r.algorithm_metrics}
        for r in results
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    # 2. Save CSV
    csv_path = output_dir / "sybil_resilience.csv"
    rows = []
    for r in results:
        for method, metrics in r.algorithm_metrics.items():
            row = {"clone_count": r.clone_count, "method": method}
            row.update(metrics)
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    logger.info("Saved experiment data to %s and %s", json_path, csv_path)

    return results


def print_experiment_summary(results: List[SybilExperimentResult]) -> None:
    """Print clean Rich table of Sybil resilience metrics."""
    console = Console()
    table = Table(title="ChainTrust Sybil & Collusion Resilience Benchmark", show_header=True, header_style="bold cyan")
    table.add_column("Clone Count", justify="center")
    table.add_column("Method", style="bold")
    table.add_column("Top-K Preserved", justify="center")
    table.add_column("Kendall's Tau", justify="right")
    table.add_column("Sybil Best Rank", justify="right")

    for r in results:
        for method, metrics in r.algorithm_metrics.items():
            pres = "[bold green]YES[/bold green]" if metrics["top_k_preserved"] == 1.0 else "[bold red]NO[/bold red]"
            tau_style = "green" if metrics["kendall_tau"] >= 0.8 else ("yellow" if metrics["kendall_tau"] >= 0.5 else "red")
            table.add_row(
                str(r.clone_count),
                method,
                pres,
                f"[{tau_style}]{metrics['kendall_tau']:.4f}[/{tau_style}]",
                str(metrics["sybil_best_rank"]),
            )

    console.print(table)
