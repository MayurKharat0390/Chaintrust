"""
chaintrust/verifier/__main__.py
CLI for third-party verification of audit bundles.
Usage:
    python -m chaintrust.verifier path/to/bundle.json [--on-chain]
"""

from __future__ import annotations

import argparse
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chaintrust.verifier.verifier import StandaloneVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description="ChainTrust Independent Audit Verifier")
    parser.add_argument("bundle", help="Path to audit bundle JSON file")
    parser.add_argument("--on-chain", action="store_true", help="Also verify against on-chain anchor")
    args = parser.parse_args()

    console = Console()
    console.print(f"[bold cyan]Auditing bundle:[/bold cyan] {args.bundle}")

    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(args.bundle, check_on_chain=args.on_chain)

    table = Table(title="ChainTrust Audit Verification Checklist", show_header=True)
    table.add_column("Verification Step", style="bold")
    table.add_column("Status", justify="center")

    def _badge(val: bool | None) -> str:
        if val is True:
            return "[bold green]PASS[/bold green]"
        elif val is False:
            return "[bold red]FAIL[/bold red]"
        return "[dim]SKIPPED[/dim]"

    table.add_row("1. Canonical Record Leaf Hashing", _badge(res.leaves_valid))
    table.add_row("2. Merkle Root Reconstruction", _badge(res.merkle_root_valid))
    table.add_row("3. Cryptographic Inclusion Proofs", _badge(res.proofs_valid))
    table.add_row(f"4. Mathematical Score Recomputation ({res.claimed_score:.4f} vs {res.recomputed_score:.4f})", _badge(res.score_recomputed_valid))
    table.add_row("5. Score Commitment Hash", _badge(res.score_hash_valid))
    if args.on_chain:
        table.add_row("6. On-Chain Anchor Commitment", _badge(res.on_chain_valid))

    console.print(table)

    if res.valid:
        console.print(Panel("[bold green]VERIFICATION SUCCESSFUL: The bundle is mathematically and cryptographically authentic![/bold green]"))
        return 0
    else:
        err_msg = "\n".join(f"- {e}" for e in res.errors)
        console.print(Panel(f"[bold red]VERIFICATION FAILED:[/bold red]\n{err_msg}"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
