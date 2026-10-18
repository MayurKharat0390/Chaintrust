"""
chaintrust/api/main.py
FastAPI REST API service for ChainTrust.
Provides endpoints for agents, tasks, reputation scores, anchors, and cryptographic audit verification.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chaintrust.anchoring.bundle import create_epoch_bundle
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.config import get_config
from chaintrust.db.models import Agent, Anchor, Interaction, Reputation, Task
from chaintrust.db.session import get_session, init_db
from chaintrust.experiments.runner import run_sybil_experiments
from chaintrust.reputation.engine import ReputationEngine
from chaintrust.verifier.verifier import StandaloneVerifier

logger = logging.getLogger("chaintrust.api")

# Ensure DB tables exist
try:
    init_db()
except Exception as e:
    logger.debug("init_db note: %s", e)

app = FastAPI(
    title="ChainTrust API",
    version="0.1.0",
    description="Real-Agent Reputation Pipeline with Blockchain Anchoring",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VerifyRequest(BaseModel):
    bundle: Dict[str, Any]
    check_on_chain: bool = False


class ComputeReputationRequest(BaseModel):
    epoch: Optional[int] = None
    methods: Optional[List[str]] = None


class AnchorRequest(BaseModel):
    agent_id: str
    epoch: int
    method: str = "tracerank"


@app.get("/health")
def health() -> Dict[str, Any]:
    cfg = get_config()
    return {
        "status": "healthy",
        "project": cfg.get("project", {}).get("name", "ChainTrust"),
        "version": cfg.get("project", {}).get("version", "0.1.0"),
    }


@app.get("/api/agents")
def get_agents() -> List[Dict[str, Any]]:
    with get_session() as session:
        agents = session.query(Agent).all()
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "provider": a.provider,
                "model": a.model,
                "stake": a.stake,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in agents
        ]


@app.get("/api/tasks")
def get_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    with get_session() as session:
        tasks = session.query(Task).limit(limit).all()
        return [
            {
                "task_id": t.task_id,
                "source": t.source.value if hasattr(t.source, "value") else str(t.source),
                "entry_point": t.entry_point,
                "difficulty_weight": t.difficulty_weight,
            }
            for t in tasks
        ]


@app.get("/api/reputation/leaderboard")
def get_leaderboard(
    method: str = Query("tracerank", description="Reputation method"),
    epoch: Optional[int] = Query(None, description="Epoch number"),
) -> List[Dict[str, Any]]:
    with get_session() as session:
        q = session.query(Reputation, Agent).join(Agent, Reputation.agent_id == Agent.agent_id)
        q = q.filter(Reputation.method == method)
        if epoch is not None:
            q = q.filter(Reputation.epoch == epoch)
        else:
            # Get latest epoch available
            latest_epoch = session.query(Reputation.epoch).order_by(Reputation.epoch.desc()).first()
            if latest_epoch:
                q = q.filter(Reputation.epoch == latest_epoch[0])

        rows = q.order_by(Reputation.score.desc()).all()
        return [
            {
                "agent_id": rep.agent_id,
                "name": ag.name,
                "provider": ag.provider,
                "model": ag.model,
                "epoch": rep.epoch,
                "method": rep.method,
                "score": rep.score,
                "computed_at": rep.computed_at.isoformat() if rep.computed_at else None,
            }
            for rep, ag in rows
        ]


@app.get("/api/reputation/comparison")
def get_reputation_comparison() -> Dict[str, Any]:
    with get_session() as session:
        reps = session.query(Reputation).all()
        agents = {a.agent_id: a.name for a in session.query(Agent).all()}
        matrix: Dict[str, Dict[str, Any]] = {}
        for r in reps:
            if r.agent_id not in matrix:
                matrix[r.agent_id] = {
                    "agent_id": r.agent_id,
                    "name": agents.get(r.agent_id, "Unknown"),
                    "scores": {},
                }
            matrix[r.agent_id]["scores"][r.method] = r.score
        return {"agents": list(matrix.values())}


@app.get("/api/anchors")
def get_anchors() -> List[Dict[str, Any]]:
    with get_session() as session:
        anchors = session.query(Anchor).order_by(Anchor.epoch.desc()).all()
        return [
            {
                "id": a.id,
                "agent_id": a.agent_id,
                "epoch": a.epoch,
                "merkle_root": a.merkle_root,
                "score_hash": a.score_hash,
                "tx_hash": a.tx_hash,
                "block_number": a.block_number,
                "anchored_at": a.anchored_at.isoformat() if a.anchored_at else None,
            }
            for a in anchors
        ]


@app.post("/api/reputation/compute")
def trigger_compute_reputation(req: ComputeReputationRequest = Body(...)) -> Dict[str, Any]:
    with get_session() as session:
        engine = ReputationEngine()
        results = engine.compute_epoch_scores(session, epoch=req.epoch or 1, methods=req.methods)
        return {"status": "success", "results": results}


@app.post("/api/anchoring/anchor")
def trigger_anchor(req: AnchorRequest = Body(...)) -> Dict[str, Any]:
    with get_session() as session:
        # Fetch agent interactions
        inters = session.query(Interaction).filter_by(agent_id=req.agent_id).all()
        if not inters:
            raise HTTPException(status_code=404, detail="No interactions found for agent")

        # Fetch score
        rep = (
            session.query(Reputation)
            .filter_by(agent_id=req.agent_id, epoch=req.epoch, method=req.method)
            .first()
        )
        score = rep.score if rep else 0.5

        # Create bundle
        bundle, path = create_epoch_bundle(
            agent_id=req.agent_id,
            epoch=req.epoch,
            interactions=inters,
            method=req.method,
            score=score,
        )

        # Anchor on chain
        client = ChainClient()
        anchor_res = client.anchor_root(
            agent_id=req.agent_id,
            epoch=req.epoch,
            merkle_root=bundle["metadata"]["merkle_root"],
            score_hash=bundle["metadata"]["score_hash"],
            session=session,
        )

        return {
            "status": "success",
            "bundle_path": str(path),
            "merkle_root": bundle["metadata"]["merkle_root"],
            "score_hash": bundle["metadata"]["score_hash"],
            "tx_hash": anchor_res.get("tx_hash"),
            "block_number": anchor_res.get("block_number"),
        }


@app.post("/api/verify")
def verify_audit_bundle(req: VerifyRequest = Body(...)) -> Dict[str, Any]:
    verifier = StandaloneVerifier()
    res = verifier.verify_bundle(req.bundle, check_on_chain=req.check_on_chain)
    return res.to_dict()


@app.get("/api/experiments/resilience")
def get_sybil_resilience(refresh: bool = False) -> List[Dict[str, Any]]:
    exp_file = Path("data/experiments/sybil_resilience.json")
    if exp_file.exists() and not refresh:
        with open(exp_file, "r", encoding="utf-8") as f:
            return json.load(f)

class LiveExecuteRequest(BaseModel):
    agent_id: str
    task_id: str


@app.post("/api/runner/execute-live")
def execute_task_live(req: LiveExecuteRequest = Body(...)) -> Dict[str, Any]:
    from chaintrust.runner.clients import get_client
    from chaintrust.runner.extractor import extract_code
    from chaintrust.grader.sandbox import Grader
    from chaintrust.anchoring.merkle import compute_interaction_leaf, interaction_to_record
    import hashlib
    from datetime import datetime, timezone

    with get_session() as session:
        agent = session.query(Agent).get(req.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        task = session.query(Task).get(req.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Reconstruct agent config
        try:
            agent_config = json.loads(agent.config_json)
        except Exception:
            agent_config = {
                "name": agent.name,
                "provider": agent.provider,
                "model": agent.model,
                "temperature": 0.2,
                "max_tokens": 1024,
                "system_prompt": "You are an expert Python programmer. Respond with ONLY python code."
            }

        client = get_client(agent_config)
        t_start = datetime.now(timezone.utc)

        # 1. LLM Generation
        try:
            gen_result = client.generate(task.prompt)
            gen_error = None
        except Exception as exc:
            gen_result = None
            gen_error = str(exc)

        if not gen_result:
            return {
                "status": "failed",
                "phase": "generation",
                "error": gen_error,
                "agent_name": agent.name,
                "task_id": task.task_id,
            }

        # 2. Extract Code
        code = extract_code(gen_result.text, strategy="fence_first", entry_point=task.entry_point)

        # 3. Grade in Sandbox
        grader = Grader()
        grade = grader.grade(
            solution_code=code,
            tests=task.tests,
            entry_point=task.entry_point,
        )

        raw_hash = hashlib.sha256(gen_result.text.encode("utf-8")).hexdigest()

        # 4. Save/Update Interaction
        existing = (
            session.query(Interaction)
            .filter_by(agent_id=agent.agent_id, task_id=task.task_id, attempt=1)
            .first()
        )
        if existing:
            existing.passed = grade.passed
            existing.tests_passed = grade.tests_passed
            existing.tests_total = grade.tests_total
            existing.quality_score = grade.quality_score
            existing.runtime_ms = grade.runtime_ms
            existing.error_type = grade.error_type
            existing.stderr_excerpt = grade.stderr_excerpt
            existing.tokens_in = gen_result.tokens_in
            existing.tokens_out = gen_result.tokens_out
            existing.latency_ms = gen_result.latency_ms
            existing.raw_output_hash = raw_hash
            existing.timestamp = t_start
            session.flush()
            interaction = existing
        else:
            interaction = Interaction(
                agent_id=agent.agent_id,
                task_id=task.task_id,
                attempt=1,
                passed=grade.passed,
                tests_passed=grade.tests_passed,
                tests_total=grade.tests_total,
                quality_score=grade.quality_score,
                runtime_ms=grade.runtime_ms,
                error_type=grade.error_type,
                stderr_excerpt=grade.stderr_excerpt,
                tokens_in=gen_result.tokens_in,
                tokens_out=gen_result.tokens_out,
                latency_ms=gen_result.latency_ms,
                raw_output_hash=raw_hash,
                timestamp=t_start,
            )
            session.add(interaction)
            session.flush()

        # Compute cryptographic leaf for Merkle tree
        rec = interaction_to_record(interaction)
        leaf_hash = compute_interaction_leaf(rec)

        # 5. Recompute dynamic reputation scores immediately
        engine = ReputationEngine()
        new_scores = engine.compute_epoch_scores(session, epoch=1)

        # Get updated ranks for this agent
        agent_scores = {
            m: new_scores.get(m, {}).get(agent.agent_id, 0.0)
            for m in engine.SUPPORTED_METHODS
        }

        # Calculate agent rank in TraceRank
        tr_scores = new_scores.get("tracerank", {})
        ranked_agents = sorted(tr_scores.items(), key=lambda x: x[1], reverse=True)
        agent_rank = next((idx + 1 for idx, (aid, _) in enumerate(ranked_agents) if aid == agent.agent_id), None)

        return {
            "status": "success",
            "agent_id": agent.agent_id,
            "agent_name": agent.name,
            "provider": agent.provider,
            "model": agent.model,
            "task_id": task.task_id,
            "entry_point": task.entry_point,
            "prompt": task.prompt,
            "tests": task.tests,
            "raw_output": gen_result.text,
            "extracted_code": code,
            "tokens_in": gen_result.tokens_in,
            "tokens_out": gen_result.tokens_out,
            "latency_ms": gen_result.latency_ms,
            "grade": {
                "passed": grade.passed,
                "tests_passed": grade.tests_passed,
                "tests_total": grade.tests_total,
                "quality_score": grade.quality_score,
                "runtime_ms": grade.runtime_ms,
                "error_type": grade.error_type,
                "stderr": grade.stderr_excerpt,
            },
            "cryptography": {
                "raw_output_sha256": raw_hash,
                "merkle_leaf_hash": leaf_hash,
            },
            "reputation": {
                "scores": agent_scores,
                "tracerank_rank": agent_rank,
                "total_agents": len(ranked_agents),
            }
        }


@app.get("/api/bundles")
def list_bundles() -> List[str]:
    bundles_dir = Path("data/bundles")
    if not bundles_dir.exists():
        return []
    return [f.name for f in bundles_dir.glob("*.json")]


@app.get("/api/bundles/{filename}")
def get_bundle(filename: str) -> Dict[str, Any]:
    safe_name = Path(filename).name
    bundle_path = Path("data/bundles") / safe_name
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail="Bundle file not found")
    with open(bundle_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Static HTML/CSS/Bootstrap frontend routes
_STATIC_DIR = Path(__file__).parent.parent / "dashboard" / "static"


@app.get("/")
@app.get("/dashboard")
def serve_dashboard():
    index_file = _STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "ChainTrust API is running. HTML dashboard not found."}


if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static_assets")
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static_root")
