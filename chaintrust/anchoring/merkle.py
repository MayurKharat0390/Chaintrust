"""
chaintrust/anchoring/merkle.py
Cryptographic Merkle tree implementation using keccak256 over canonical interaction records.
Handles deterministic canonical JSON serialisation, odd-leaf duplication, Merkle root generation,
and inclusion proof generation and verification.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from eth_hash.auto import keccak


def keccak256(data: bytes) -> bytes:
    """Compute 32-byte keccak256 hash of bytes."""
    return keccak(data)


def keccak256_hex(data: bytes) -> str:
    """Compute 0x-prefixed hex string of keccak256 hash."""
    return "0x" + keccak256(data).hex()


def canonical_json(obj: Any) -> str:
    """
    Produce deterministic canonical JSON:
    - Dict keys sorted alphabetically
    - No extra whitespace (separators=(',', ':'))
    - Datetimes formatted as ISO 8601 strings
    - Floats rounded to 6 decimal places
    """
    def _default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, float):
            return round(o, 6)
        return str(o)

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def interaction_to_record(
    interaction: Any,
    leaf_version: int = 1,
    epoch: Optional[int] = None,
    family: Optional[Sequence[str] | Tuple[str, str]] = None,
    params_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract canonical dictionary representation from an Interaction ORM object or dict.
    Supports backward-compatible leaf_version=1 and Level A leaf_version=2.
    """
    if isinstance(interaction, dict):
        rec_ver = int(interaction.get("leaf_version", leaf_version))
        rec_epoch = int(epoch if epoch is not None else interaction.get("epoch", 1))
        fam = family if family is not None else interaction.get("family", ["unknown", "unknown"])
        fam_list = [str(fam[0]), str(fam[1])] if isinstance(fam, (list, tuple)) and len(fam) >= 2 else ["unknown", "unknown"]
        p_hash = params_hash if params_hash is not None else interaction.get("params_hash", "")

        base_rec = {
            "agent_id": str(interaction.get("agent_id", "")),
            "attempt": int(interaction.get("attempt", 1)),
            "difficulty_weight": round(float(interaction.get("difficulty_weight", 0.5)), 6),
            "id": int(interaction.get("id", 0)),
            "passed": bool(interaction.get("passed", False)),
            "quality_score": round(float(interaction.get("quality_score", 0.0)), 6),
            "raw_output_hash": str(interaction.get("raw_output_hash", "") or ""),
            "task_id": str(interaction.get("task_id", "")),
            "tests_passed": int(interaction.get("tests_passed", 0)),
            "tests_total": int(interaction.get("tests_total", 0)),
            "timestamp": interaction.get("timestamp").isoformat() if hasattr(interaction.get("timestamp"), "isoformat") else str(interaction.get("timestamp", "")),
        }
        if rec_ver >= 2:
            base_rec["leaf_version"] = rec_ver
            base_rec["epoch"] = rec_epoch
            base_rec["family"] = fam_list
            base_rec["params_hash"] = str(p_hash or "")
        return base_rec

    ts = getattr(interaction, "timestamp", None)
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
    diff = getattr(interaction, "difficulty_weight", None)
    diff_val = round(float(diff), 6) if diff is not None else 0.5

    rec_epoch = int(epoch if epoch is not None else getattr(interaction, "epoch", 1))
    fam = family if family is not None else getattr(interaction, "family", ["unknown", "unknown"])
    fam_list = [str(fam[0]), str(fam[1])] if isinstance(fam, (list, tuple)) and len(fam) >= 2 else ["unknown", "unknown"]
    p_hash = params_hash if params_hash is not None else getattr(interaction, "params_hash", "")

    base_rec = {
        "agent_id": str(getattr(interaction, "agent_id", "")),
        "attempt": int(getattr(interaction, "attempt", 1)),
        "difficulty_weight": diff_val,
        "id": int(getattr(interaction, "id", 0)),
        "passed": bool(getattr(interaction, "passed", False)),
        "quality_score": round(float(getattr(interaction, "quality_score", 0.0)), 6),
        "raw_output_hash": str(getattr(interaction, "raw_output_hash", "") or ""),
        "task_id": str(getattr(interaction, "task_id", "")),
        "tests_passed": int(getattr(interaction, "tests_passed", 0)),
        "tests_total": int(getattr(interaction, "tests_total", 0)),
        "timestamp": ts_str,
    }
    if leaf_version >= 2:
        base_rec["leaf_version"] = leaf_version
        base_rec["epoch"] = rec_epoch
        base_rec["family"] = fam_list
        base_rec["params_hash"] = str(p_hash or "")
    return base_rec


def compute_interaction_leaf(
    interaction: Any,
    leaf_version: int = 1,
    epoch: Optional[int] = None,
    family: Optional[Sequence[str] | Tuple[str, str]] = None,
    params_hash: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (leaf_hash_0x_hex, canonical_record_dict) for an interaction.
    """
    record = interaction_to_record(
        interaction,
        leaf_version=leaf_version,
        epoch=epoch,
        family=family,
        params_hash=params_hash,
    )
    payload = canonical_json(record).encode("utf-8")
    leaf_hash = keccak256_hex(payload)
    return leaf_hash, record


def compute_difficulty_leaf(task_id: str, difficulty_val: float) -> Tuple[str, Dict[str, Any]]:
    """Compute canonical record and leaf hash for a task difficulty entry."""
    rec = {
        "difficulty": round(float(difficulty_val), 6),
        "task_id": str(task_id),
    }
    payload = canonical_json(rec).encode("utf-8")
    leaf_hash = keccak256_hex(payload)
    return leaf_hash, rec


def build_difficulty_tree(difficulty_table: Dict[str, float]) -> Tuple[MerkleTree, str, List[Dict[str, Any]]]:
    """
    Build a Merkle tree over the epoch task difficulty table (task_id -> d_t).
    Sorted deterministically by task_id.
    Returns:
        (tree, difficulty_root, table_records_with_proofs)
    """
    sorted_tasks = sorted(difficulty_table.keys())
    leaf_hashes: List[str] = []
    records: List[Dict[str, Any]] = []

    for tid in sorted_tasks:
        h, rec = compute_difficulty_leaf(tid, difficulty_table[tid])
        leaf_hashes.append(h)
        records.append(rec)

    tree = MerkleTree(leaf_hashes)
    table_records_with_proofs: List[Dict[str, Any]] = []

    for i, rec in enumerate(records):
        proof = tree.get_proof(i)
        rec_with_proof = dict(rec)
        rec_with_proof["proof"] = proof
        table_records_with_proofs.append(rec_with_proof)

    return tree, tree.root, table_records_with_proofs


def verify_difficulty_leaf(task_id: str, difficulty_val: float, proof: List[str], root: str) -> bool:
    """Verify that a task difficulty entry is included in the difficulty Merkle root."""
    leaf_hash, _ = compute_difficulty_leaf(task_id, difficulty_val)
    return verify_merkle_proof(leaf_hash, proof, root)


class MerkleTree:
    """
    Complete binary Merkle Tree built with keccak256.
    Leaves are sorted or preserved in canonical interaction order.
    Odd-count layers duplicate the last node.
    """

    def __init__(self, leaf_hashes: List[str]):
        """
        leaf_hashes: List of 0x-prefixed hex strings.
        """
        self.leaf_hashes = [h if h.startswith("0x") else "0x" + h for h in leaf_hashes]
        self.layers: List[List[bytes]] = []
        self._build()

    def _build(self) -> None:
        if not self.leaf_hashes:
            self.root_bytes = b"\x00" * 32
            self.layers = [[]]
            return

        current_layer = [bytes.fromhex(h[2:]) for h in self.leaf_hashes]
        self.layers.append(current_layer)

        while len(current_layer) > 1:
            next_layer: List[bytes] = []
            # If odd count, duplicate last element
            if len(current_layer) % 2 == 1:
                current_layer = list(current_layer) + [current_layer[-1]]

            for i in range(0, len(current_layer), 2):
                left = current_layer[i]
                right = current_layer[i + 1]
                parent = keccak256(left + right)
                next_layer.append(parent)

            current_layer = next_layer
            self.layers.append(current_layer)

        self.root_bytes = self.layers[-1][0] if self.layers[-1] else b"\x00" * 32

    @property
    def root(self) -> str:
        """Returns 0x-prefixed 32-byte hex string."""
        return "0x" + self.root_bytes.hex()

    def get_proof(self, index: int) -> List[Dict[str, str]]:
        """
        Generates Merkle audit proof for leaf at index.
        Returns list of dicts: [{"sibling": "0x...", "position": "left" | "right"}]
        """
        if index < 0 or index >= len(self.leaf_hashes):
            raise IndexError("Leaf index out of bounds")

        proof: List[Dict[str, str]] = []
        curr_idx = index

        for layer_idx in range(len(self.layers) - 1):
            layer = self.layers[layer_idx]
            # Account for odd duplication in that layer
            effective_layer = list(layer)
            if len(effective_layer) % 2 == 1:
                effective_layer.append(effective_layer[-1])

            if curr_idx % 2 == 0:
                # Sibling is on the right
                sibling_idx = curr_idx + 1
                pos = "right"
            else:
                # Sibling is on the left
                sibling_idx = curr_idx - 1
                pos = "left"

            sibling_bytes = effective_layer[sibling_idx]
            proof.append({
                "sibling": "0x" + sibling_bytes.hex(),
                "position": pos,
            })
            curr_idx //= 2

        return proof


def verify_merkle_proof(
    leaf_hash: str,
    proof: List[Dict[str, str]],
    root_hash: str,
) -> bool:
    """
    Verifies that leaf_hash belongs to the Merkle tree with root_hash.
    """
    curr = bytes.fromhex(leaf_hash[2:] if leaf_hash.startswith("0x") else leaf_hash)
    target_root = bytes.fromhex(root_hash[2:] if root_hash.startswith("0x") else root_hash)

    for step in proof:
        sibling = bytes.fromhex(step["sibling"][2:] if step["sibling"].startswith("0x") else step["sibling"])
        pos = step.get("position", "right")

        if pos == "left":
            curr = keccak256(sibling + curr)
        else:
            curr = keccak256(curr + sibling)

    return curr == target_root


def rating_to_record(rating: Any) -> Dict[str, Any]:
    """
    Extract canonical dictionary representation of a PeerRating ORM object or dict.
    Sorted keys: justification, ratee_id, rater_id, rating, raw_output_hash, task_id, timestamp.
    """
    if isinstance(rating, dict):
        ts = rating.get("timestamp")
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
        return {
            "justification": str(rating.get("justification", "") or ""),
            "ratee_id": str(rating.get("ratee_id", "")),
            "rater_id": str(rating.get("rater_id", "")),
            "rating": round(float(rating.get("rating", 0.0)), 6),
            "raw_output_hash": str(rating.get("raw_output_hash", "") or ""),
            "task_id": str(rating.get("task_id", "")),
            "timestamp": ts_str,
        }

    ts = getattr(rating, "timestamp", None)
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
    return {
        "justification": str(getattr(rating, "justification", "") or ""),
        "ratee_id": str(getattr(rating, "ratee_id", "")),
        "rater_id": str(getattr(rating, "rater_id", "")),
        "rating": round(float(getattr(rating, "rating", 0.0)), 6),
        "raw_output_hash": str(getattr(rating, "raw_output_hash", "") or ""),
        "task_id": str(getattr(rating, "task_id", "")),
        "timestamp": ts_str,
    }


def compute_rating_leaf(rating: Any) -> Tuple[str, Dict[str, Any]]:
    """Returns (leaf_hash_0x_hex, canonical_record_dict) for a peer review rating."""
    rec = rating_to_record(rating)
    payload = canonical_json(rec).encode("utf-8")
    leaf_hash = keccak256_hex(payload)
    return leaf_hash, rec


def build_ratings_tree(ratings: Sequence[Any]) -> Tuple[MerkleTree, str, List[Dict[str, Any]]]:
    """
    Build a Merkle tree over the epoch peer ratings graph.
    Sorted deterministically by (rater_id, ratee_id, task_id).
    Returns:
        (tree, ratings_root, ratings_records_with_proofs)
    """
    def _sort_key(r: Any) -> Tuple[str, str, str]:
        if isinstance(r, dict):
            return (str(r.get("rater_id", "")), str(r.get("ratee_id", "")), str(r.get("task_id", "")))
        return (str(getattr(r, "rater_id", "")), str(getattr(r, "ratee_id", "")), str(getattr(r, "task_id", "")))

    sorted_ratings = sorted(ratings, key=_sort_key)
    leaf_hashes: List[str] = []
    records: List[Dict[str, Any]] = []

    for r in sorted_ratings:
        h, rec = compute_rating_leaf(r)
        leaf_hashes.append(h)
        records.append(rec)

    tree = MerkleTree(leaf_hashes)
    records_with_proofs: List[Dict[str, Any]] = []

    for i, rec in enumerate(records):
        proof = tree.get_proof(i)
        rec_with_proof = dict(rec)
        rec_with_proof["proof"] = proof
        records_with_proofs.append(rec_with_proof)

    return tree, tree.root, records_with_proofs


def verify_rating_leaf(rating: Any, proof: Sequence[Dict[str, str]], root: str) -> bool:
    """Verify that a peer rating is in the Merkle tree with root."""
    leaf_hash, _ = compute_rating_leaf(rating)
    return verify_merkle_proof(leaf_hash, list(proof), root)

