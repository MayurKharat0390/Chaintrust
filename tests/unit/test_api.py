"""
tests/unit/test_api.py
Unit tests for FastAPI endpoints in ChainTrust.
"""

import pytest
from starlette.testclient import TestClient

from chaintrust.anchoring.bundle import create_epoch_bundle
from chaintrust.api.main import app
from chaintrust.db.session import init_db


@pytest.fixture
def client():
    init_db()
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "ChainTrust"


def test_get_agents_endpoint(client):
    response = client.get("/api/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_tasks_endpoint(client):
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_leaderboard_endpoint(client):
    response = client.get("/api/reputation/leaderboard?method=tracerank")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_anchors_endpoint(client):
    response = client.get("/api/anchors")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_verify_bundle_endpoint(client, tmp_path):
    # Create a small valid test bundle
    agent_id = "agent_api_test"
    epoch = 1
    inters = [
        {
            "id": 1,
            "agent_id": agent_id,
            "task_id": "t1",
            "attempt": 1,
            "passed": True,
            "tests_passed": 5,
            "tests_total": 5,
            "quality_score": 1.0,
            "difficulty_weight": 0.5,
            "raw_output_hash": "0x123",
            "timestamp": "2026-10-15T00:00:00Z",
        }
    ]
    bundle, _ = create_epoch_bundle(
        agent_id=agent_id,
        epoch=epoch,
        interactions=inters,
        method="simple_avg",
        score=1.0,
        output_dir=str(tmp_path),
    )

    response = client.post("/api/verify", json={"bundle": bundle, "check_on_chain": False})
    assert response.status_code == 200
    res = response.json()
    assert res["valid"] is True
    assert res["merkle_root_valid"] is True
    assert res["score_recomputed_valid"] is True


def test_get_leaderboard_chs_endpoint(client):
    response = client.get("/api/reputation/leaderboard?method=chs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        assert data[0]["method"] == "chs"
        assert "params_hash" in data[0]


def test_get_reputation_comparison_endpoint(client):
    response = client.get("/api/reputation/comparison")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "methods" in data
    assert "spearman_correlation" in data
    assert "kendall_correlation" in data
    assert "chs" in data["methods"]


def test_get_chs_breakdown_endpoint(client):
    response = client.get("/api/reputation/chs/breakdown")
    assert response.status_code == 200
    data = response.json()
    assert "epoch" in data
    assert "params_hash" in data
    assert "agents" in data
    assert isinstance(data["agents"], list)
    if data["agents"]:
        first = data["agents"][0]
        assert "d_prime" in first
        assert "c_a" in first
        assert "t_tilde" in first
        assert "pi_a" in first
        assert "score" in first


def test_get_experiments_results_endpoint(client):
    response = client.get("/api/experiments/results")
    assert response.status_code == 200
    data = response.json()
    assert "experiments" in data
    assert len(data["experiments"]) >= 6
    exp_ids = [e["id"] for e in data["experiments"]]
    assert "experiment_a" in exp_ids
    assert "experiment_b" in exp_ids
    assert "experiment_f" in exp_ids


