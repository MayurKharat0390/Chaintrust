"""
chaintrust/experiments/__main__.py
CLI entry-point to execute adversarial and Sybil benchmarks.
Usage:
    python -m chaintrust.experiments
"""

from __future__ import annotations

import sys
from rich.console import Console

from chaintrust.config import get_config
from chaintrust.experiments.runner import print_experiment_summary, run_sybil_experiments


def main() -> int:
    console = Console()
    console.print("[bold yellow]Executing ChainTrust Adversarial Resilience Experiments...[/bold yellow]")

    try:
        config = get_config()
        results = run_sybil_experiments(config)
        print_experiment_summary(results)
        console.print("[bold green]Benchmark completed successfully. Data saved to data/experiments/[/bold green]")
        return 0
    except Exception as e:
        console.print(f"[bold red]Experiment failed:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
