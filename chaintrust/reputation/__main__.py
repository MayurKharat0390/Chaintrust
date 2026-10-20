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
        help="Methods to compute: simple_avg weighted pagerank eigentrust tracerank chs elo beta",
    )
    args = parser.parse_args()

    console = Console()
    config = get_config()

    try:
        with get_session() as session:
            engine = ReputationEngine(config)
            console.print("[bold cyan]Computing reputation scores across algorithms...[/bold cyan]")
            results = engine.compute_latest(session=session, epoch=args.epoch)

            agents = {a.agent_id: a.name for a in session.query(Agent).all()}

            # 1. Main Side-by-Side Leaderboard Table
            table = Table(title="ChainTrust Agent Reputation Scores (Multi-Method Leaderboard)", show_header=True, header_style="bold magenta")
            table.add_column("Agent Name", style="cyan")
            table.add_column("Agent ID", style="dim")

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

            # 2. Rank Correlation Matrices (Spearman & Kendall)
            if len(all_aids) >= 2 and len(methods) >= 2:
                import numpy as np
                from scipy import stats

                method_vectors = {
                    m: [results[m].get(aid, 0.0) for aid in all_aids]
                    for m in methods
                }

                corr_table = Table(title="Pairwise Rank Correlation (Spearman r / Kendall tau)", show_header=True, header_style="bold green")
                corr_table.add_column("Method", style="yellow")
                for m in methods:
                    corr_table.add_column(m, justify="center")

                for m1 in methods:
                    row = [m1]
                    v1 = method_vectors[m1]
                    for m2 in methods:
                        v2 = method_vectors[m2]
                        if m1 == m2:
                            row.append("1.00 / 1.00")
                        elif np.all(v1 == v1[0]) or np.all(v2 == v2[0]):
                            row.append("0.00 / 0.00")
                        else:
                            sp = stats.spearmanr(v1, v2).statistic
                            kd = stats.kendalltau(v1, v2).statistic
                            sp_str = f"{0.0 if np.isnan(sp) else sp:.2f}"
                            kd_str = f"{0.0 if np.isnan(kd) else kd:.2f}"
                            row.append(f"{sp_str} / {kd_str}")
                    corr_table.add_row(*row)

                console.print(corr_table)

            return 0
    except Exception as e:
        console.print(f"[bold red]Error computing reputation:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
