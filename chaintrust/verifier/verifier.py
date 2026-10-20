"""
chaintrust/verifier/verifier.py
Standalone cryptographic and mathematical audit verifier for ChainTrust.
Enables any third-party to independently verify without database access:
1. Merkle root integrity (reconstructing tree from leaves)
2. Leaf inclusion proofs
3. Raw interaction record hashes
4. Exact mathematical score recomputation
5. Cryptographic score commitment hash
6. Level A CHS verification: difficulty table Merkle root, parameters hash, and direct score recomputation
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chaintrust.anchoring.bundle import compute_chs_score_hash, compute_score_hash, load_bundle
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.anchoring.merkle import (
    MerkleTree,
    canonical_json,
    compute_difficulty_leaf,
    compute_rating_leaf,
    keccak256_hex,
    verify_merkle_proof,
)
from chaintrust.reputation.algorithms import get_scorer
from chaintrust.reputation.chs import (
    CHSParams,
    compute_params_hash,
    defense,
    direct_scores,
    propagate,
)


def _parse_iso_time(ts_val: Any) -> Optional[datetime]:
    if not ts_val:
        return None
    if isinstance(ts_val, datetime):
        return ts_val
    try:
        return datetime.fromisoformat(str(ts_val).replace("Z", "+00:00"))
    except Exception:
        return None


class VerificationResult:
    """Detailed results of an audit verification run."""

    def __init__(self) -> None:
        self.valid: bool = True
        self.merkle_root_valid: bool = False
        self.leaves_valid: bool = False
        self.proofs_valid: bool = False
        self.score_recomputed_valid: bool = False
        self.score_hash_valid: bool = False
        self.difficulty_root_valid: Optional[bool] = None
        self.ratings_root_valid: Optional[bool] = None
        self.params_hash_valid: Optional[bool] = None
        self.confidence_valid: Optional[bool] = None
        self.level_a_valid: Optional[bool] = None
        self.level_b_valid: Optional[bool] = None
        self.on_chain_valid: Optional[bool] = None
        self.recomputed_score: float = 0.0
        self.claimed_score: float = 0.0
        self.direct_score: float = 0.0
        self.confidence: float = 0.0
        self.t_tilde: float = 0.0
        self.defense_penalty: float = 0.0
        self.errors: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "merkle_root_valid": self.merkle_root_valid,
            "leaves_valid": self.leaves_valid,
            "proofs_valid": self.proofs_valid,
            "score_recomputed_valid": self.score_recomputed_valid,
            "score_hash_valid": self.score_hash_valid,
            "difficulty_root_valid": self.difficulty_root_valid,
            "ratings_root_valid": self.ratings_root_valid,
            "params_hash_valid": self.params_hash_valid,
            "confidence_valid": self.confidence_valid,
            "level_a_valid": self.level_a_valid,
            "level_b_valid": self.level_b_valid,
            "on_chain_valid": self.on_chain_valid,
            "claimed_score": self.claimed_score,
            "recomputed_score": self.recomputed_score,
            "direct_score": self.direct_score,
            "confidence": self.confidence,
            "t_tilde": self.t_tilde,
            "defense_penalty": self.defense_penalty,
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
            version = metadata.get("version", "1.0")
            claimed_score = float(metadata.get("score", 0.0))
            claimed_score_hash = metadata.get("score_hash")
            claimed_root = metadata.get("merkle_root")

            records = bundle.get("records", [])
            leaf_hashes = bundle.get("leaf_hashes", [])
            proofs = bundle.get("proofs", [])

            result.claimed_score = claimed_score

            is_chs = (method == "chs" or version == "2.0-chs" or "difficulty_root" in metadata)

            if is_chs:
                return self._verify_chs(
                    bundle=bundle,
                    result=result,
                    agent_id=agent_id,
                    epoch=epoch,
                    claimed_score=claimed_score,
                    claimed_score_hash=claimed_score_hash,
                    claimed_root=claimed_root,
                    records=records,
                    leaf_hashes=leaf_hashes,
                    proofs=proofs,
                    check_on_chain=check_on_chain,
                )

            # ----------------- Legacy / Standard Bundle Verification -----------------
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

            ref_time = _parse_iso_time(metadata.get("created_at"))

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

    def _verify_chs(
        self,
        bundle: Dict[str, Any],
        result: VerificationResult,
        agent_id: str,
        epoch: int,
        claimed_score: float,
        claimed_score_hash: str,
        claimed_root: str,
        records: List[Dict[str, Any]],
        leaf_hashes: List[str],
        proofs: List[List[Dict[str, str]]],
        check_on_chain: bool = False,
    ) -> VerificationResult:
        """
        Independent Level A CHS verification:
        1. Leaf hash check on all canonical interaction records (leaf_version=2).
        2. Merkle root integrity and leaf inclusion proofs.
        3. Difficulty table Merkle verification against claimed difficulty_root.
        4. Parameters integrity check against claimed params_hash.
        5. Exact mathematical recomputation of Level A direct score and confidence.
        6. Cryptographic score hash commitment verification.
        """
        metadata = bundle.get("metadata", {})
        claimed_params_hash = metadata.get("params_hash")
        claimed_diff_root = metadata.get("difficulty_root")

        # 1. Check leaf hashes
        computed_leaf_hashes: List[str] = []
        leaves_match = True
        for i, rec in enumerate(records):
            payload = canonical_json(rec).encode("utf-8")
            h = keccak256_hex(payload)
            computed_leaf_hashes.append(h)
            if i < len(leaf_hashes) and h != leaf_hashes[i]:
                leaves_match = False
                result.errors.append(f"Leaf hash mismatch at index {i}: claimed {leaf_hashes[i]} vs computed {h}")
            if rec.get("leaf_version", 1) >= 2 and claimed_params_hash:
                if rec.get("params_hash") != claimed_params_hash:
                    leaves_match = False
                    result.errors.append(
                        f"Record params_hash mismatch at index {i}: {rec.get('params_hash')} vs claimed {claimed_params_hash}"
                    )

        result.leaves_valid = leaves_match and len(records) == len(leaf_hashes)

        # 2. Check record Merkle root
        tree = MerkleTree(computed_leaf_hashes)
        result.merkle_root_valid = (tree.root == claimed_root)
        if not result.merkle_root_valid:
            result.errors.append(f"Merkle root mismatch: claimed {claimed_root} vs reconstructed {tree.root}")

        # 3. Check record inclusion proofs
        all_proofs_valid = True
        for i, proof in enumerate(proofs):
            if i >= len(computed_leaf_hashes):
                break
            leaf = computed_leaf_hashes[i]
            if not verify_merkle_proof(leaf, proof, claimed_root):
                all_proofs_valid = False
                result.errors.append(f"Merkle inclusion proof failed for record leaf {i}")

        result.proofs_valid = all_proofs_valid

        # 4. Check difficulty table and its Merkle root
        diff_entries = bundle.get("difficulty_table", [])
        if not claimed_diff_root:
            result.difficulty_root_valid = False
            result.errors.append("Missing difficulty_root in bundle metadata")
        elif not diff_entries:
            result.difficulty_root_valid = False
            result.errors.append("Missing difficulty_table in bundle")
        else:
            diff_leaves: List[str] = []
            all_diff_proofs_valid = True
            sorted_diffs = sorted(diff_entries, key=lambda x: str(x.get("task_id", "")))
            for d_idx, d_entry in enumerate(sorted_diffs):
                tid = str(d_entry.get("task_id", ""))
                dval = float(d_entry.get("difficulty", 0.5))
                d_leaf, _ = compute_difficulty_leaf(tid, dval)
                diff_leaves.append(d_leaf)
                proof = d_entry.get("proof", [])
                if not verify_merkle_proof(d_leaf, proof, claimed_diff_root):
                    all_diff_proofs_valid = False
                    result.errors.append(f"Difficulty inclusion proof failed for task {tid}")

            diff_tree = MerkleTree(diff_leaves)
            if diff_tree.root != claimed_diff_root:
                result.difficulty_root_valid = False
                result.errors.append(
                    f"Difficulty Merkle root mismatch: claimed {claimed_diff_root} vs reconstructed {diff_tree.root}"
                )
            else:
                result.difficulty_root_valid = all_diff_proofs_valid

        # 5. Check parameters and params_hash
        raw_params = bundle.get("parameters", {})
        chs_params: Optional[CHSParams] = None
        if not raw_params:
            result.params_hash_valid = False
            result.errors.append("Missing parameters dictionary in bundle")
        else:
            try:
                chs_params = CHSParams(**raw_params)
                computed_phash = compute_params_hash(chs_params)
                result.params_hash_valid = (computed_phash == claimed_params_hash)
                if not result.params_hash_valid:
                    result.errors.append(
                        f"Parameters hash mismatch: claimed {claimed_params_hash} vs computed {computed_phash}"
                    )
            except Exception as pe:
                result.params_hash_valid = False
                result.errors.append(f"Failed to parse CHS parameters: {pe}")

        # Check if bundle contains Level B ratings graph
        is_level_b = (
            "ratings_root" in metadata
            or "ratings_table" in bundle
            or metadata.get("verification_level") == "B"
        )

        # 6. Ratings graph Merkle verification if Level B
        if is_level_b:
            ratings_entries = bundle.get("ratings_table", [])
            claimed_ratings_root = metadata.get("ratings_root")
            if not claimed_ratings_root:
                result.ratings_root_valid = False
                result.errors.append("Missing ratings_root in Level B bundle metadata")
            elif not ratings_entries:
                result.ratings_root_valid = False
                result.errors.append("Missing ratings_table in Level B bundle")
            else:
                ratings_leaves: List[str] = []
                all_ratings_proofs_valid = True
                sorted_ratings = sorted(
                    ratings_entries,
                    key=lambda r: (str(r.get("rater_id", "")), str(r.get("ratee_id", "")), str(r.get("task_id", "")))
                )
                for r_entry in sorted_ratings:
                    r_leaf, _ = compute_rating_leaf(r_entry)
                    ratings_leaves.append(r_leaf)
                    proof = r_entry.get("proof", [])
                    if not verify_merkle_proof(r_leaf, proof, claimed_ratings_root):
                        all_ratings_proofs_valid = False
                        result.errors.append(
                            f"Rating inclusion proof failed for {r_entry.get('rater_id')} -> {r_entry.get('ratee_id')}"
                        )

                ratings_tree = MerkleTree(ratings_leaves)
                if ratings_tree.root != claimed_ratings_root:
                    result.ratings_root_valid = False
                    result.errors.append(
                        f"Ratings Merkle root mismatch: claimed {claimed_ratings_root} vs reconstructed {ratings_tree.root}"
                    )
                else:
                    result.ratings_root_valid = all_ratings_proofs_valid
        else:
            result.ratings_root_valid = None

        # 7. Recompute scores
        if chs_params is not None and result.difficulty_root_valid and result.params_hash_valid:
            ref_time = _parse_iso_time(metadata.get("as_of") or metadata.get("created_at"))
            diff_lookup = {str(d.get("task_id")): float(d.get("difficulty", 0.5)) for d in diff_entries}

            if is_level_b and result.ratings_root_valid:
                bundle_agents = bundle.get("agents") or [
                    {"agent_id": agent_id, "stake": int(metadata.get("stake", 0)), "family": ["unknown", "unknown"]}
                ]
                direct_dict, n_dict, conf_dict = direct_scores(
                    records,
                    diff_lookup,
                    chs_params,
                    as_of=ref_time,
                    agents=bundle_agents,
                )
                t_tilde_map = propagate(direct_dict, n_dict, bundle_agents, ratings_entries, chs_params)
                penalty_map = defense(ratings_entries, bundle_agents, chs_params)

                D_prime_a = direct_dict.get(agent_id, 0.5)
                C_a = conf_dict.get(agent_id, 1.0)
                t_tilde_a = t_tilde_map.get(agent_id, D_prime_a)
                pi_a = penalty_map.get(agent_id, 0.0)

                recomputed_b = round(
                    (C_a ** chs_params.omega)
                    * ((1.0 - chs_params.w) * D_prime_a + chs_params.w * t_tilde_a)
                    * (1.0 - pi_a),
                    6,
                )
                result.recomputed_score = recomputed_b
                result.direct_score = round(float(D_prime_a), 6)
                result.confidence = round(float(C_a), 6)
                result.t_tilde = round(float(t_tilde_a), 6)
                result.defense_penalty = round(float(pi_a), 6)

                result.score_recomputed_valid = (abs(recomputed_b - claimed_score) < 1e-4)
                if not result.score_recomputed_valid:
                    result.errors.append(
                        f"Level B score recomputation mismatch: claimed {claimed_score:.6f} vs recomputed {recomputed_b:.6f}"
                    )
            else:
                direct_dict, n_dict, conf_dict = direct_scores(
                    records,
                    diff_lookup,
                    chs_params,
                    as_of=ref_time,
                    agents=[agent_id],
                )
                recomputed = round(float(direct_dict.get(agent_id, 0.5)), 6)
                conf_val = round(float(conf_dict.get(agent_id, 0.0)), 6)
                result.recomputed_score = recomputed
                result.direct_score = recomputed
                result.confidence = conf_val

                result.score_recomputed_valid = (abs(recomputed - claimed_score) < 1e-4)
                if not result.score_recomputed_valid:
                    result.errors.append(
                        f"Score recomputation mismatch: claimed {claimed_score:.6f} vs recomputed {recomputed:.6f}"
                    )

            if metadata.get("confidence") is not None:
                claimed_conf = float(metadata.get("confidence", 0.0))
                result.confidence_valid = (abs(result.confidence - claimed_conf) < 1e-4)
                if not result.confidence_valid:
                    result.errors.append(
                        f"Confidence recomputation mismatch: claimed {claimed_conf:.6f} vs recomputed {result.confidence:.6f}"
                    )
            else:
                result.confidence_valid = True
        else:
            result.score_recomputed_valid = False

        # 8. Check score commitment hash
        expected_score_hash = compute_score_hash(agent_id, epoch, "chs", claimed_score)
        result.score_hash_valid = (expected_score_hash == claimed_score_hash)
        if not result.score_hash_valid:
            result.errors.append(
                f"Score hash mismatch: claimed {claimed_score_hash} vs expected {expected_score_hash}"
            )

        # 9. Check on-chain anchor if requested
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

        # Level A validity
        result.level_a_valid = bool(
            result.leaves_valid
            and result.merkle_root_valid
            and result.proofs_valid
            and result.difficulty_root_valid
            and result.params_hash_valid
            and result.score_recomputed_valid
            and result.score_hash_valid
        )

        # Level B validity
        if is_level_b:
            result.level_b_valid = bool(
                result.level_a_valid
                and result.ratings_root_valid
                and result.score_recomputed_valid
            )
            result.valid = result.level_b_valid and (result.on_chain_valid is not False)
        else:
            result.level_b_valid = None
            result.valid = result.level_a_valid and (result.on_chain_valid is not False)

        return result


def verify_chs_bundle(
    bundle_input: str | Path | Dict[str, Any],
    check_on_chain: bool = False,
    chain_client: Optional[ChainClient] = None,
) -> VerificationResult:
    """
    Convenience function to independently verify a Level A CHS audit bundle.
    Reads only the bundle without database or network access (unless check_on_chain=True).
    """
    verifier = StandaloneVerifier(chain_client=chain_client)
    return verifier.verify_bundle(bundle_input, check_on_chain=check_on_chain)
