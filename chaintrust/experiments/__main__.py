"""
chaintrust/experiments/__main__.py
CLI entry-point to execute ChainTrust adversarial, validity, and Sybil benchmarks.
Usage:
    python -m chaintrust.experiments
    python -m chaintrust.experiments --experiment=A
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from chaintrust.experiments.suite import (
    run_all_experiments,
    run_experiment_a,
    run_experiment_b,
    run_experiment_c,
    run_experiment_d,
    run_experiment_e,
    run_experiment_f,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="ChainTrust Empirical Benchmark Suite")
    parser.add_argument(
        "--experiment",
        "-e",
        choices=["A", "B", "C", "D", "E", "F", "all"],
        default="all",
        help="Specific experiment to run (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="experiments/results",
        help="Directory to save CSV data and PNG charts",
    )

    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    console = Console()

    try:
        exp = args.experiment.upper()
        if exp == "ALL":
            run_all_experiments(output_dir=out_dir)
        elif exp == "A":
            console.print("[bold yellow]Running Experiment A (Validity)...[/bold yellow]")
            df = run_experiment_a(output_dir=out_dir)
            console.print(df)
        elif exp == "B":
            console.print("[bold yellow]Running Experiment B (Sybil Clones)...[/bold yellow]")
            df = run_experiment_b(output_dir=out_dir)
            console.print(df)
        elif exp == "C":
            console.print("[bold yellow]Running Experiment C (Collusion Ring)...[/bold yellow]")
            df = run_experiment_c(output_dir=out_dir)
            console.print(df)
        elif exp == "D":
            console.print("[bold yellow]Running Experiment D (Ablations)...[/bold yellow]")
            df = run_experiment_d(output_dir=out_dir)
            console.print(df)
        elif exp == "E":
            console.print("[bold yellow]Running Experiment E (Sensitivity)...[/bold yellow]")
            df = run_experiment_e(output_dir=out_dir)
            console.print(df)
        elif exp == "F":
            console.print("[bold yellow]Running Experiment F (Tamper Detection)...[/bold yellow]")
            df = run_experiment_f(output_dir=out_dir)
            console.print(df)

        return 0
    except Exception as e:
        console.print(f"[bold red]Experiment failed with error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
