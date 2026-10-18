"""
chaintrust/reputation/__main__.py
CLI entry-point to trigger reputation score computation for the current database state.
"""

from __future__ import annotations

import argparse
import sys
from rich.console import Console
from rich.table import Table

from chaintrust.config import get_config
from chaintrust.db.models import Agent
from chaintrust.db.session import get_session
from chaintrust.reputation.engine import ReputationEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="ChainTrust Reputation Engine CLI")
    parser.add_argument("--epoch", type=int, default=None, help="Specific epoch number to compute")
    parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Methods to compute: simple_avg weighted pagerank eigentrust tracerank",
    )
    args = parser.parse_args()

    console = Console()
    config = get_config()

    try:
        with get_session() as session:
            engine = ReputationEngine(config)
            console.print("[bold cyan]Computing reputation scores...[/bold cyan]")
            results = engine.compute_latest(session=session, epoch=args.epoch)

            agents = {a.agent_id: a.name for a in session.query(Agent).all()}

            table = Table(title="ChainTrust Agent Reputation Scores", show_header=True, header_style="bold magenta")
            table.add_column("Agent Name", style="cyan")
            table.add_column("Agent ID (prefix)", style="dim")

            methods = list(results.keys())
            for m in methods:
                table.add_column(m, justify="right")

            all_aids = sorted(list({aid for m in methods for aid in results[m].keys()}))

            for aid in all_aids:
                name = agents.get(aid, "Unknown")
                row = [name, aid[:8]]
                for m in methods:
                    score = results[m].get(aid, 0.0)
                    row.append(f"{score:.4f}")
                table.add_row(*row)

            console.print(table)
            return 0
    except Exception as e:
        console.print(f"[bold red]Error computing reputation:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
