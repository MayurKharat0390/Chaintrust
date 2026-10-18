"""
chaintrust/verifier/verifier.py
Standalone cryptographic and mathematical audit verifier for ChainTrust.
Enables any third-party to independently verify:
1. Merkle root integrity (reconstructing tree from leaves)
2. Leaf inclusion proofs
3. Raw interaction record hashes
4. Exact mathematical score recomputation
5. Cryptographic score commitment hash
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chaintrust.anchoring.bundle import compute_score_hash, load_bundle
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.anchoring.merkle import (
    MerkleTree,
    canonical_json,
    keccak256_hex,
    verify_merkle_proof,
)
from chaintrust.reputation.algorithms import get_scorer


class VerificationResult:
    """Detailed results of an audit verification run."""

    def __init__(self) -> None:
        self.valid: bool = True
        self.merkle_root_valid: bool = False
        self.leaves_valid: bool = False
        self.proofs_valid: bool = False
        self.score_recomputed_valid: bool = False
        self.score_hash_valid: bool = False
        self.on_chain_valid: Optional[bool] = None
        self.recomputed_score: float = 0.0
        self.claimed_score: float = 0.0
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "merkle_root_valid": self.merkle_root_valid,
            "leaves_valid": self.leaves_valid,
            "proofs_valid": self.proofs_valid,
            "score_recomputed_valid": self.score_recomputed_valid,
            "score_hash_valid": self.score_hash_valid,
            "on_chain_valid": self.on_chain_valid,
            "claimed_score": self.claimed_score,
            "recomputed_score": self.recomputed_score,
            "errors": self.errors,
        }


class StandaloneVerifier:
    """
    Independent verifier capable of verifying an audit bundle without database access.
    """

    def __init__(self, chain_client: Optional[ChainClient] = None):
        self.chain_client = chain_client or ChainClient()

    def verify_bundle(
        self,
        bundle_input: str | Path | Dict[str, Any],
        check_on_chain: bool = False,
    ) -> VerificationResult:
        result = VerificationResult()

        try:
            if isinstance(bundle_input, (str, Path)):
                bundle = load_bundle(bundle_input)
            else:
                bundle = bundle_input

            metadata = bundle.get("metadata", {})
            agent_id = metadata.get("agent_id")
            epoch = metadata.get("epoch")
            method = metadata.get("method", "tracerank")
            claimed_score = float(metadata.get("score", 0.0))
            claimed_score_hash = metadata.get("score_hash")
            claimed_root = metadata.get("merkle_root")

            records = bundle.get("records", [])
            leaf_hashes = bundle.get("leaf_hashes", [])
            proofs = bundle.get("proofs", [])

            result.claimed_score = claimed_score

            # 1. Check leaf hash validity
            computed_leaf_hashes: List[str] = []
            leaves_match = True
            for i, rec in enumerate(records):
                payload = canonical_json(rec).encode("utf-8")
                h = keccak256_hex(payload)
                computed_leaf_hashes.append(h)
                if i < len(leaf_hashes) and h != leaf_hashes[i]:
                    leaves_match = False
                    result.errors.append(f"Leaf hash mismatch at index {i}: claimed {leaf_hashes[i]} vs computed {h}")

            result.leaves_valid = leaves_match and len(records) == len(leaf_hashes)

            # 2. Check Merkle root integrity
            tree = MerkleTree(computed_leaf_hashes)
            reconstructed_root = tree.root
            result.merkle_root_valid = (reconstructed_root == claimed_root)
            if not result.merkle_root_valid:
                result.errors.append(f"Merkle root mismatch: claimed {claimed_root} vs reconstructed {reconstructed_root}")

            # 3. Check all individual proofs
            all_proofs_valid = True
            for i, proof in enumerate(proofs):
                if i >= len(computed_leaf_hashes):
                    break
                leaf = computed_leaf_hashes[i]
                if not verify_merkle_proof(leaf, proof, claimed_root):
                    all_proofs_valid = False
                    result.errors.append(f"Merkle inclusion proof failed for leaf {i}")

            result.proofs_valid = all_proofs_valid

            # 4. Independent score recomputation
            scorer = get_scorer(method)
            agent_obj = {"agent_id": agent_id, "stake": int(metadata.get("stake", 0))}
            task_diffs = {r.get("task_id"): float(r.get("difficulty_weight", 0.5)) for r in records}

            ref_time = None
            if metadata.get("created_at"):
                try:
                    ref_time = datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
                except Exception:
                    ref_time = None

            recomputed_scores = scorer.compute(
                interactions=records,
                agents=[agent_obj],
                task_difficulties=task_diffs,
                reference_time=ref_time,
            )
            recomputed = round(float(recomputed_scores.get(agent_id, 0.0)), 6)
            result.recomputed_score = recomputed

            # Check within rounding tolerance
            result.score_recomputed_valid = abs(recomputed - claimed_score) < 1e-4
            if not result.score_recomputed_valid:
                result.errors.append(
                    f"Score recomputation mismatch: claimed {claimed_score:.6f} vs recomputed {recomputed:.6f}"
                )

            # 5. Check score hash commitment
            expected_score_hash = compute_score_hash(agent_id, epoch, method, claimed_score)
            result.score_hash_valid = (expected_score_hash == claimed_score_hash)
            if not result.score_hash_valid:
                result.errors.append(
                    f"Score hash mismatch: claimed {claimed_score_hash} vs expected {expected_score_hash}"
                )

            # 6. Check on-chain anchor if requested
            if check_on_chain:
                anchor = self.chain_client.get_anchor(agent_id, epoch)
                if anchor:
                    on_chain_root = anchor.get("merkle_root")
                    on_chain_shash = anchor.get("score_hash")
                    result.on_chain_valid = (on_chain_root == claimed_root and on_chain_shash == claimed_score_hash)
                    if not result.on_chain_valid:
                        result.errors.append("On-chain anchor record does not match claimed bundle values")
                else:
                    result.on_chain_valid = False
                    result.errors.append(f"No on-chain anchor found for agent {agent_id} at epoch {epoch}")

            # Overall validity
            result.valid = (
                result.leaves_valid
                and result.merkle_root_valid
                and result.proofs_valid
                and result.score_recomputed_valid
                and result.score_hash_valid
                and (result.on_chain_valid is not False)
            )

        except Exception as e:
            result.valid = False
            result.errors.append(f"Verification exception: {str(e)}")

        return result
