"""
tests/unit/test_anchoring_and_verifier.py
Unit tests for Merkle tree construction, inclusion proofs, audit bundle creation,
and independent third-party verification.
"""

from datetime import datetime, timezone
import json
import pytest

from chaintrust.anchoring.bundle import compute_score_hash, create_epoch_bundle
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.anchoring.merkle import (
    MerkleTree,
    canonical_json,
    compute_interaction_leaf,
    keccak256_hex,
    verify_merkle_proof,
)
from chaintrust.verifier.verifier import StandaloneVerifier


class DummyInteraction:
    def __init__(self, id_val: int, agent_id: str, task_id: str, quality_score: float):
        self.id = id_val
        self.agent_id = agent_id
        self.task_id = task_id
        self.attempt = 1
        self.passed = quality_score >= 1.0
        self.tests_passed = int(quality_score * 10)
        self.tests_total = 10
        self.quality_score = quality_score
        self.raw_output_hash = "0x" + "a" * 64
        self.difficulty_weight = 0.5
        self.timestamp = datetime.now(timezone.utc)


class TestMerkleTree:
    def test_single_leaf(self):
        leaf = "0x" + "11" * 32
        tree = MerkleTree([leaf])
        assert tree.root == leaf

    def test_odd_leaves_duplication(self):
        leaves = ["0x" + "11" * 32, "0x" + "22" * 32, "0x" + "33" * 32]
        tree = MerkleTree(leaves)
        assert tree.root.startswith("0x")
        assert len(tree.root) == 66

    def test_merkle_proof_verification_success(self):
        leaves = [
            "0x" + "aa" * 32,
            "0x" + "bb" * 32,
            "0x" + "cc" * 32,
            "0x" + "dd" * 32,
            "0x" + "ee" * 32,
        ]
        tree = MerkleTree(leaves)
        root = tree.root

        for idx, leaf in enumerate(leaves):
            proof = tree.get_proof(idx)
            assert verify_merkle_proof(leaf, proof, root) is True

    def test_merkle_proof_verification_fails_tampered_leaf(self):
        leaves = ["0x" + "aa" * 32, "0x" + "bb" * 32]
        tree = MerkleTree(leaves)
        root = tree.root
        proof = tree.get_proof(0)
        tampered_leaf = "0x" + "99" * 32
        assert verify_merkle_proof(tampered_leaf, proof, root) is False


class TestBundleAndVerifier:
    def test_bundle_creation_and_independent_verification(self, tmp_path):
        agent_id = "test_agent_alpha"
        epoch = 1
        method = "simple_avg"

        inters = [
            DummyInteraction(1, agent_id, "task_1", 1.0),
            DummyInteraction(2, agent_id, "task_2", 0.6),
            DummyInteraction(3, agent_id, "task_3", 0.8),
        ]
        # Average is (1.0 + 0.6 + 0.8) / 3 = 0.800000
        score = 0.800000

        bundle, bundle_path = create_epoch_bundle(
            agent_id=agent_id,
            epoch=epoch,
            interactions=inters,
            method=method,
            score=score,
            output_dir=str(tmp_path),
        )

        assert bundle_path.exists()
        assert bundle["metadata"]["merkle_root"].startswith("0x")
        assert len(bundle["records"]) == 3
        assert len(bundle["leaf_hashes"]) == 3

        # Run standalone verification
        verifier = StandaloneVerifier()
        result = verifier.verify_bundle(bundle_path)

        assert result.valid is True
        assert result.merkle_root_valid is True
        assert result.leaves_valid is True
        assert result.proofs_valid is True
        assert result.score_recomputed_valid is True
        assert result.score_hash_valid is True
        assert len(result.errors) == 0

    def test_verifier_catches_tampered_record(self, tmp_path):
        agent_id = "test_agent_beta"
        epoch = 1
        method = "simple_avg"

        inters = [
            DummyInteraction(1, agent_id, "task_1", 1.0),
            DummyInteraction(2, agent_id, "task_2", 0.0),
        ]
        score = 0.500000

        bundle, bundle_path = create_epoch_bundle(
            agent_id=agent_id,
            epoch=epoch,
            interactions=inters,
            method=method,
            score=score,
            output_dir=str(tmp_path),
        )

        # Tamper with record score in the file
        with open(bundle_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["records"][1]["quality_score"] = 1.0  # Falsely claims passed
        with open(bundle_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        verifier = StandaloneVerifier()
        result = verifier.verify_bundle(bundle_path)

        assert result.valid is False
        assert len(result.errors) > 0


class TestChainClient:
    def test_simulated_anchoring(self):
        client = ChainClient()
        res = client.anchor_root(
            agent_id="agent_123",
            epoch=1,
            merkle_root="0x" + "11" * 32,
            score_hash="0x" + "22" * 32,
        )
        assert res["tx_hash"].startswith("0x")
        assert res["block_number"] > 0

        # Check retrieval
        anchor = client.get_anchor("agent_123", 1)
        assert anchor is not None
        assert anchor["merkle_root"] == "0x" + "11" * 32
