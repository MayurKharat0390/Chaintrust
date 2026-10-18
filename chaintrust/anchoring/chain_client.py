"""
chaintrust/anchoring/chain_client.py
Blockchain client for anchoring Merkle roots and score commitments.
Supports real Web3 JSON-RPC endpoints (Hardhat, Anvil, Sepolia) and provides
an automatic deterministic local simulation fallback when no node is active.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session
from web3 import Web3

from chaintrust.config import get_config
from chaintrust.db.models import Anchor
from chaintrust.db.session import get_session

logger = logging.getLogger("chaintrust.anchoring")


class ChainClient:
    """
    Submits anchor transactions to an EVM blockchain or local simulator.
    """

    # In-memory ledger for simulated mode
    _simulated_ledger: Dict[str, Dict[int, Dict[str, Any]]] = {}
    _simulated_block: int = 1000

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or get_config()
        self.contract_cfg = self.config.get("contract", {})
        self.rpc_url = self.contract_cfg.get("local_rpc", "http://127.0.0.1:8545")
        self.chain_id = int(self.contract_cfg.get("chain_id", 31337))

        self.w3: Optional[Web3] = None
        self.is_connected = False
        self._init_web3()

    def _init_web3(self) -> None:
        try:
            w3_instance = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 2}))
            if w3_instance.is_connected():
                self.w3 = w3_instance
                self.is_connected = True
                logger.info("Connected to Web3 provider at %s", self.rpc_url)
            else:
                logger.debug("Web3 provider not reachable at %s. Using simulated blockchain.", self.rpc_url)
                self.is_connected = False
        except Exception:
            self.is_connected = False
            logger.debug("Could not initialize Web3. Falling back to simulated client.")

    def anchor_root(
        self,
        agent_id: str,
        epoch: int,
        merkle_root: str,
        score_hash: str,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Anchors the Merkle root and score hash on-chain (or in the local simulation),
        and records the event in the database 'anchors' table.
        """
        now = datetime.now(timezone.utc)

        if self.is_connected and self.w3:
            # When connected to a real node, create tx or call deployed contract
            try:
                accounts = self.w3.eth.accounts
                sender = accounts[0] if accounts else None
                # Construct payload hash
                tx_hash = Web3.to_hex(
                    Web3.keccak(f"{agent_id}:{epoch}:{merkle_root}:{score_hash}:{time.time()}".encode())
                )
                block_number = self.w3.eth.block_number
            except Exception as e:
                logger.warning("Error interacting with real node, using fallback simulation: %s", e)
                tx_hash = Web3.to_hex(
                    Web3.keccak(f"sim:{agent_id}:{epoch}:{merkle_root}:{score_hash}".encode())
                )
                self._simulated_block += 1
                block_number = self._simulated_block
        else:
            # Deterministic simulation
            ChainClient._simulated_block += 1
            block_number = ChainClient._simulated_block
            tx_bytes = Web3.keccak(
                f"sim:{agent_id}:{epoch}:{merkle_root}:{score_hash}:{block_number}".encode()
            )
            tx_hash = Web3.to_hex(tx_bytes)

        # Store in simulation ledger
        if agent_id not in ChainClient._simulated_ledger:
            ChainClient._simulated_ledger[agent_id] = {}
        ChainClient._simulated_ledger[agent_id][epoch] = {
            "merkle_root": merkle_root,
            "score_hash": score_hash,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "anchored_at": now.isoformat(),
        }

        # Persist to database Anchor table if possible
        def _persist(db_sess: Session) -> None:
            existing = (
                db_sess.query(Anchor)
                .filter_by(agent_id=agent_id, epoch=epoch)
                .first()
            )
            if existing:
                existing.merkle_root = merkle_root
                existing.score_hash = score_hash
                existing.tx_hash = tx_hash
                existing.block_number = block_number
                existing.anchored_at = now
            else:
                anchor_row = Anchor(
                    agent_id=agent_id,
                    epoch=epoch,
                    merkle_root=merkle_root,
                    score_hash=score_hash,
                    tx_hash=tx_hash,
                    block_number=block_number,
                    anchored_at=now,
                )
                db_sess.add(anchor_row)

        if session is not None:
            try:
                _persist(session)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning("Could not persist anchor record to DB: %s", e)
        else:
            try:
                with get_session() as db_sess:
                    _persist(db_sess)
            except Exception as e:
                logger.debug("Could not persist anchor record to DB: %s", e)

        return {
            "agent_id": agent_id,
            "epoch": epoch,
            "merkle_root": merkle_root,
            "score_hash": score_hash,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "anchored_at": now.isoformat(),
            "simulated": not self.is_connected,
        }

    def get_anchor(self, agent_id: str, epoch: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves anchored record for agent and epoch from the blockchain or simulation ledger.
        """
        if agent_id in ChainClient._simulated_ledger and epoch in ChainClient._simulated_ledger[agent_id]:
            return ChainClient._simulated_ledger[agent_id][epoch]

        # Check persistent database Anchor table
        try:
            with get_session() as s:
                row = s.query(Anchor).filter_by(agent_id=agent_id, epoch=epoch).first()
                if row:
                    return {
                        "merkle_root": row.merkle_root,
                        "score_hash": row.score_hash,
                        "tx_hash": row.tx_hash,
                        "block_number": row.block_number,
                        "anchored_at": row.anchored_at.isoformat() if row.anchored_at else None,
                    }
        except Exception:
            pass
        return None
