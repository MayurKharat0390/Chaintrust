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


def interaction_to_record(interaction: Any) -> Dict[str, Any]:
    """
    Extract canonical dictionary representation from an Interaction ORM object or dict.
    """
    if isinstance(interaction, dict):
        return {
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

    ts = getattr(interaction, "timestamp", None)
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")
    diff = getattr(interaction, "difficulty_weight", None)
    diff_val = round(float(diff), 6) if diff is not None else 0.5

    return {
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


def compute_interaction_leaf(interaction: Any) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (leaf_hash_0x_hex, canonical_record_dict) for an interaction.
    """
    record = interaction_to_record(interaction)
    payload = canonical_json(record).encode("utf-8")
    leaf_hash = keccak256_hex(payload)
    return leaf_hash, record


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
