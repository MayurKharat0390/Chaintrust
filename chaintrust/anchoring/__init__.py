"""
chaintrust/anchoring/__init__.py
Merkle tree anchoring and blockchain commitment module.
"""

from chaintrust.anchoring.bundle import (
    compute_score_hash,
    create_epoch_bundle,
    load_bundle,
)
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.anchoring.merkle import (
    MerkleTree,
    canonical_json,
    compute_interaction_leaf,
    interaction_to_record,
    keccak256,
    keccak256_hex,
    verify_merkle_proof,
)

__all__ = [
    "MerkleTree",
    "keccak256",
    "keccak256_hex",
    "canonical_json",
    "interaction_to_record",
    "compute_interaction_leaf",
    "verify_merkle_proof",
    "compute_score_hash",
    "create_epoch_bundle",
    "load_bundle",
    "ChainClient",
]
