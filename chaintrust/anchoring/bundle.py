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
    build_difficulty_tree,
    build_ratings_tree,
    canonical_json,
    compute_interaction_leaf,
    keccak256_hex,
)
from chaintrust.reputation.chs import (
    CHSParams,
    chs,
    compute_params_hash,
    defense,
    direct_scores,
    load_chs_params,
    propagate,
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
    method: str = "chs",
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


def compute_chs_score_hash(agent_id: str, epoch: int, score: float) -> str:
    """
    Computes cryptographic commitment hash for a claimed CHS score:
    keccak256(canonical_json({"agent_id": ..., "epoch": ..., "method": "chs", "score": round(score, 6)}))
    """
    return compute_score_hash(agent_id, epoch, "chs", score)


def create_chs_audit_bundle(
    agent_id: str,
    epoch: int,
    interactions: Sequence[Any],
    difficulty_table: Dict[str, float],
    params: Optional[CHSParams | Dict[str, Any]] = None,
    ratings: Optional[Sequence[Any]] = None,
    agents: Optional[Sequence[Any]] = None,
    score: Optional[float] = None,
    stake: int = 0,
    as_of: Optional[datetime] = None,
    output_dir: Optional[str] = None,
) -> Tuple[Dict[str, Any], Path]:
    """
    Generates a Level A (or Level B if ratings provided) CHS audit bundle (.audit.json).
    Includes:
      - Canonical records with leaf_version=2 and params_hash
      - Record Merkle proofs against merkle_root
      - Difficulty table Merkle proofs against difficulty_root
      - Optional ratings table with Merkle proofs against ratings_root (Level B)
      - CHS parameters dictionary and params_hash
      - as_of timestamp and score commitment hash
    Returns:
        (bundle_dict, saved_path)
    """
    if params is None:
        chs_params = load_chs_params()
    elif isinstance(params, dict):
        chs_params = CHSParams(**params)
    else:
        chs_params = params

    params_hash = compute_params_hash(chs_params)
    as_of_dt = as_of or datetime.now(timezone.utc)

    # Build difficulty tree
    diff_tree, diff_root, diff_table_records = build_difficulty_tree(difficulty_table)

    # Sort interactions deterministically by id
    sorted_inters = sorted(
        interactions,
        key=lambda x: getattr(x, "id", 0) if hasattr(x, "id") else x.get("id", 0)
    )

    leaf_hashes: List[str] = []
    canonical_records: List[Dict[str, Any]] = []

    for inter in sorted_inters:
        t_id = getattr(inter, "task_id", "") if hasattr(inter, "task_id") else inter.get("task_id", "")
        diff_val = difficulty_table.get(t_id, 0.5)

        if isinstance(inter, dict):
            inter_dict = dict(inter)
            if "difficulty_weight" not in inter_dict or inter_dict["difficulty_weight"] is None:
                inter_dict["difficulty_weight"] = diff_val
            inter_dict["params_hash"] = params_hash
            leaf_hash, record = compute_interaction_leaf(
                inter_dict,
                leaf_version=2,
                epoch=epoch,
                params_hash=params_hash,
            )
        else:
            if getattr(inter, "difficulty_weight", None) is None:
                try:
                    inter.difficulty_weight = diff_val
                except Exception:
                    pass
            leaf_hash, record = compute_interaction_leaf(
                inter,
                leaf_version=2,
                epoch=epoch,
                params_hash=params_hash,
            )
        leaf_hashes.append(leaf_hash)
        canonical_records.append(record)

    tree = MerkleTree(leaf_hashes)
    merkle_root = tree.root

    proofs = [tree.get_proof(i) for i in range(len(leaf_hashes))]

    # Default single-agent context if none provided
    if agents is None:
        agents_list = [{"agent_id": agent_id, "stake": int(stake), "family": ["unknown", "unknown"]}]
    else:
        agents_list = list(agents)

    # Direct scores (Layer 1)
    direct_dict, n_dict, conf_dict = direct_scores(
        canonical_records,
        difficulty_table,
        chs_params,
        as_of=as_of_dt,
        agents=agents_list,
    )
    direct_score_val = direct_dict.get(agent_id, 0.5)
    conf_val = conf_dict.get(agent_id, 0.0)

    # Level B handling if ratings provided
    ratings_root: Optional[str] = None
    ratings_table_records: List[Dict[str, Any]] = []
    t_tilde_val: float = direct_score_val
    penalty_val: float = 0.0

    if ratings is not None and len(ratings) > 0:
        ratings_tree, ratings_root, ratings_table_records = build_ratings_tree(ratings)
        t_tilde_map = propagate(direct_dict, n_dict, agents_list, ratings, chs_params)
        penalty_map = defense(ratings, agents_list, chs_params)

        t_tilde_val = t_tilde_map.get(agent_id, direct_score_val)
        penalty_val = penalty_map.get(agent_id, 0.0)
        recomputed_score = round(
            (conf_val ** chs_params.omega)
            * ((1.0 - chs_params.w) * direct_score_val + chs_params.w * t_tilde_val)
            * (1.0 - penalty_val),
            6,
        )
        verification_level = "B"
    else:
        recomputed_score = direct_score_val
        verification_level = "A"

    final_score = round(float(recomputed_score if score is None else score), 6)
    score_hash = compute_chs_score_hash(agent_id, epoch, final_score)

    bundle_metadata: Dict[str, Any] = {
        "version": "2.0-chs",
        "verification_level": verification_level,
        "agent_id": agent_id,
        "epoch": epoch,
        "method": "chs",
        "score": final_score,
        "direct_score": round(float(direct_score_val), 6),
        "confidence": round(float(conf_val), 6),
        "stake": int(stake),
        "score_hash": score_hash,
        "merkle_root": merkle_root,
        "difficulty_root": diff_root,
        "params_hash": params_hash,
        "as_of": as_of_dt.isoformat(),
        "interaction_count": len(canonical_records),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if ratings_root is not None:
        bundle_metadata["ratings_root"] = ratings_root
        bundle_metadata["t_tilde"] = round(float(t_tilde_val), 6)
        bundle_metadata["defense_penalty"] = round(float(penalty_val), 6)

    bundle: Dict[str, Any] = {
        "metadata": bundle_metadata,
        "records": canonical_records,
        "leaf_hashes": leaf_hashes,
        "proofs": proofs,
        "difficulty_table": diff_table_records,
        "parameters": chs_params.to_dict(),
    }

    if ratings_table_records:
        bundle["ratings_table"] = ratings_table_records

    # Serialize canonical agent metadata if Level B
    if verification_level == "B":
        canonical_agents = []
        for ag in agents_list:
            aid = getattr(ag, "agent_id", None) or (ag.get("agent_id") if isinstance(ag, dict) else str(ag))
            stk = getattr(ag, "stake", None) or (ag.get("stake", 0) if isinstance(ag, dict) else 0)
            fam = getattr(ag, "family", None) or (ag.get("family", ["unknown", "unknown"]) if isinstance(ag, dict) else ["unknown", "unknown"])
            fam_list = [str(fam[0]), str(fam[1])] if isinstance(fam, (list, tuple)) and len(fam) >= 2 else ["unknown", "unknown"]
            canonical_agents.append({"agent_id": str(aid), "family": fam_list, "stake": int(stk)})
        bundle["agents"] = canonical_agents

    out_path = Path(output_dir or "data/bundles")
    out_path.mkdir(parents=True, exist_ok=True)
    file_name = f"bundle_epoch_{epoch}_{agent_id[:16]}.audit.json"
    file_path = out_path / file_name

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2, sort_keys=True)

    return bundle, file_path

