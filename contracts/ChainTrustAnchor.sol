// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ChainTrustAnchor
 * @notice Anchors AI agent reputation Merkle roots and score commitments on Ethereum.
 * Provides on-chain tamper-evidence and independent Merkle proof verification.
 */
contract ChainTrustAnchor {
    struct AnchorRecord {
        bytes32 merkleRoot;
        bytes32 scoreHash;
        uint256 timestamp;
        uint256 blockNumber;
    }

    // agentId => (epoch => AnchorRecord)
    mapping(string => mapping(uint256 => AnchorRecord)) private _anchors;

    // List of registered agent IDs
    string[] private _agentIds;
    mapping(string => bool) private _knownAgents;

    event Anchored(
        string indexed agentId,
        uint256 indexed epoch,
        bytes32 merkleRoot,
        bytes32 scoreHash,
        uint256 timestamp
    );

    /**
     * @notice Anchor an agent's Merkle root and score commitment for an epoch.
     * @param agentId Unique identifier for the agent configuration
     * @param epoch Interaction epoch sequence number
     * @param merkleRoot Keccak256 root of the agent's interaction records tree
     * @param scoreHash Keccak256 commitment of the claimed reputation score
     */
    function anchorRoot(
        string calldata agentId,
        uint256 epoch,
        bytes32 merkleRoot,
        bytes32 scoreHash
    ) external {
        require(bytes(agentId).length > 0, "Invalid agent ID");
        require(merkleRoot != bytes32(0), "Invalid Merkle root");

        AnchorRecord storage record = _anchors[agentId][epoch];
        require(record.merkleRoot == bytes32(0), "Epoch already anchored");

        record.merkleRoot = merkleRoot;
        record.scoreHash = scoreHash;
        record.timestamp = block.timestamp;
        record.blockNumber = block.number;

        if (!_knownAgents[agentId]) {
            _knownAgents[agentId] = true;
            _agentIds.push(agentId);
        }

        emit Anchored(agentId, epoch, merkleRoot, scoreHash, block.timestamp);
    }

    /**
     * @notice Retrieve an anchored record.
     */
    function getAnchor(string calldata agentId, uint256 epoch)
        external
        view
        returns (
            bytes32 merkleRoot,
            bytes32 scoreHash,
            uint256 timestamp,
            uint256 blockNumber
        )
    {
        AnchorRecord storage record = _anchors[agentId][epoch];
        require(record.merkleRoot != bytes32(0), "Anchor does not exist");
        return (
            record.merkleRoot,
            record.scoreHash,
            record.timestamp,
            record.blockNumber
        );
    }

    /**
     * @notice Check whether an anchor exists for the given agent and epoch.
     */
    function hasAnchor(string calldata agentId, uint256 epoch)
        external
        view
        returns (bool)
    {
        return _anchors[agentId][epoch].merkleRoot != bytes32(0);
    }

    /**
     * @notice Standalone on-chain Merkle proof verification helper.
     */
    function verifyInclusion(
        bytes32 leaf,
        bytes32[] calldata proof,
        bool[] calldata isLeftSibling,
        bytes32 root
    ) external pure returns (bool) {
        require(proof.length == isLeftSibling.length, "Mismatched proof arrays");
        bytes32 current = leaf;

        for (uint256 i = 0; i < proof.length; i++) {
            if (isLeftSibling[i]) {
                current = keccak256(abi.encodePacked(proof[i], current));
            } else {
                current = keccak256(abi.encodePacked(current, proof[i]));
            }
        }

        return current == root;
    }
}
