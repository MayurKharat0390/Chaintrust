"""
chaintrust/anchoring/bundle.py
Audit bundle creation, serialisation, and persistence.
A bundle contains the complete cryptographic evidence (Merkle root, leaf hashes,
inclusion proofs, canonical interaction records, score commitment hash)
needed for independent verification.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from chaintrust.anchoring.merkle import (
    MerkleTree,
    canonical_json,
    compute_interaction_leaf,
    keccak256_hex,
)


def compute_score_hash(agent_id: str, epoch: int, method: str, score: float) -> str:
    """
    Computes cryptographic commitment hash for a claimed score:
    keccak256(canonical_json({"agent_id": ..., "epoch": ..., "method": ..., "score": round(score, 6)}))
    """
    payload = canonical_json({
        "agent_id": str(agent_id),
        "epoch": int(epoch),
        "method": str(method),
        "score": round(float(score), 6),
    }).encode("utf-8")
    return keccak256_hex(payload)


def create_epoch_bundle(
    agent_id: str,
    epoch: int,
    interactions: Sequence[Any],
    method: str = "tracerank",
    score: float = 0.0,
    stake: int = 0,
    output_dir: Optional[str] = None,
) -> Tuple[Dict[str, Any], Path]:
    """
    Generates a full audit bundle for an agent's epoch interactions and writes it to disk.
    Returns:
        (bundle_dict, saved_path)
    """
    # Sort interactions deterministically by id
    sorted_inters = sorted(
        interactions,
        key=lambda x: getattr(x, "id", 0) if hasattr(x, "id") else x.get("id", 0)
    )

    leaf_hashes: List[str] = []
    canonical_records: List[Dict[str, Any]] = []

    for inter in sorted_inters:
        leaf_hash, record = compute_interaction_leaf(inter)
        leaf_hashes.append(leaf_hash)
        canonical_records.append(record)

    tree = MerkleTree(leaf_hashes)
    merkle_root = tree.root
    score_hash = compute_score_hash(agent_id, epoch, method, score)

    proofs = [tree.get_proof(i) for i in range(len(leaf_hashes))]

    bundle: Dict[str, Any] = {
        "metadata": {
            "version": "1.0",
            "agent_id": agent_id,
            "epoch": epoch,
            "method": method,
            "score": round(float(score), 6),
            "stake": int(stake),
            "score_hash": score_hash,
            "merkle_root": merkle_root,
            "interaction_count": len(sorted_inters),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "records": canonical_records,
        "leaf_hashes": leaf_hashes,
        "proofs": proofs,
    }

    out_path = Path(output_dir or "data/bundles")
    out_path.mkdir(parents=True, exist_ok=True)
    file_name = f"bundle_epoch_{epoch}_{agent_id[:16]}.json"
    file_path = out_path / file_name

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, sort_keys=True)

    return bundle, file_path


def load_bundle(file_path: str | Path) -> Dict[str, Any]:
    """Load and parse an audit bundle JSON file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audit bundle not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
