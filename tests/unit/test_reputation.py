"""
tests/unit/test_reputation.py
Unit tests for ChainTrust reputation algorithms and engine.
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chaintrust.db.models import Agent, Base, Interaction, Reputation, Task
from chaintrust.reputation.algorithms import (
    EigenTrustScorer,
    PageRankScorer,
    SimpleAverage,
    TraceRankScorer,
    WeightedHistory,
    compute_task_difficulties,
    get_scorer,
)
from chaintrust.reputation.engine import ReputationEngine


class DummyAgent:
    def __init__(self, agent_id: str, stake: int = 0):
        self.agent_id = agent_id
        self.stake = stake


class DummyInteraction:
    def __init__(
        self,
        agent_id: str,
        task_id: str,
        passed: bool,
        quality_score: float,
        timestamp: datetime,
    ):
        self.agent_id = agent_id
        self.task_id = task_id
        self.passed = passed
        self.quality_score = quality_score
        self.timestamp = timestamp


class TestTaskDifficulties:
    def test_empty_interactions(self):
        diffs = compute_task_difficulties([])
        assert diffs == {}

    def test_all_passed(self):
        now = datetime.now(timezone.utc)
        inters = [
            DummyInteraction("a1", "t1", True, 1.0, now),
            DummyInteraction("a2", "t1", True, 1.0, now),
        ]
        diffs = compute_task_difficulties(inters, d_min=0.1, d_max=1.0, smoothing=1.0)
        # (2 + 1) / (2 + 2) = 3/4 = 0.75 -> 1 - 0.75 = 0.25
        assert round(diffs["t1"], 4) == 0.25

    def test_all_failed(self):
        now = datetime.now(timezone.utc)
        inters = [
            DummyInteraction("a1", "t1", False, 0.0, now),
            DummyInteraction("a2", "t1", False, 0.0, now),
        ]
        diffs = compute_task_difficulties(inters, d_min=0.1, d_max=1.0, smoothing=1.0)
        # (0 + 1) / (2 + 2) = 1/4 = 0.25 -> 1 - 0.25 = 0.75
        assert round(diffs["t1"], 4) == 0.75


class TestSimpleAverage:
    def test_simple_average_calculation(self):
        now = datetime.now(timezone.utc)
        agents = [DummyAgent("a1"), DummyAgent("a2")]
        inters = [
            DummyInteraction("a1", "t1", True, 1.0, now),
            DummyInteraction("a1", "t2", False, 0.5, now),
            DummyInteraction("a2", "t1", True, 0.8, now),
        ]
        scorer = SimpleAverage()
        scores = scorer.compute(inters, agents)
        assert round(scores["a1"], 4) == 0.75
        assert round(scores["a2"], 4) == 0.80

    def test_agent_with_no_interactions(self):
        agents = [DummyAgent("a1")]
        scorer = SimpleAverage()
        scores = scorer.compute([], agents)
        assert scores["a1"] == 0.0


class TestWeightedHistory:
    def test_time_decay_and_difficulty(self):
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)
        agents = [DummyAgent("a1")]
        # t1 is hard (diff=0.9), t2 is easy (diff=0.2)
        task_diffs = {"t1": 0.9, "t2": 0.2}
        inters = [
            # Recent interaction on easy task
            DummyInteraction("a1", "t2", True, 1.0, now),
            # Old interaction on hard task
            DummyInteraction("a1", "t1", True, 1.0, old_time),
        ]
        scorer = WeightedHistory({"half_life_days": 30.0})
        scores = scorer.compute(inters, agents, task_difficulties=task_diffs, reference_time=now)
        assert 0.0 <= scores["a1"] <= 1.0


class TestPageRankScorer:
    def test_pagerank_computation(self):
        now = datetime.now(timezone.utc)
        agents = [DummyAgent("a1"), DummyAgent("a2")]
        inters = [
            DummyInteraction("a1", "t1", True, 1.0, now),
            DummyInteraction("a2", "t1", False, 0.0, now),
        ]
        scorer = PageRankScorer()
        scores = scorer.compute(inters, agents)
        assert "a1" in scores and "a2" in scores
        assert scores["a1"] >= scores["a2"]


class TestEigenTrustScorer:
    def test_eigentrust_stake_pretrust(self):
        now = datetime.now(timezone.utc)
        agents = [DummyAgent("a1", stake=100), DummyAgent("a2", stake=0)]
        inters = [
            DummyInteraction("a1", "t1", True, 1.0, now),
            DummyInteraction("a2", "t1", True, 1.0, now),
        ]
        scorer = EigenTrustScorer()
        scores = scorer.compute(inters, agents)
        assert "a1" in scores and "a2" in scores


class TestTraceRankScorer:
    def test_tracerank_stake_and_consistency(self):
        now = datetime.now(timezone.utc)
        agents = [DummyAgent("honest_agent", stake=50), DummyAgent("sybil_agent", stake=0)]
        inters = [
            # Honest agent: consistent high scores
            DummyInteraction("honest_agent", "t1", True, 1.0, now),
            DummyInteraction("honest_agent", "t2", True, 0.9, now),
            # Sybil agent: wild inconsistency or unweighted
            DummyInteraction("sybil_agent", "t1", True, 1.0, now),
            DummyInteraction("sybil_agent", "t2", False, 0.1, now),
        ]
        task_diffs = {"t1": 0.8, "t2": 0.8}
        scorer = TraceRankScorer({"consistency_weight": 0.5})
        scores = scorer.compute(inters, agents, task_difficulties=task_diffs, reference_time=now)
        assert scores["honest_agent"] > scores["sybil_agent"]

    def test_factory_function(self):
        for method in ["simple_avg", "weighted", "pagerank", "eigentrust", "tracerank"]:
            scorer = get_scorer(method)
            assert scorer.name == method


class TestReputationEngineIntegration:
    @pytest.fixture
    def test_session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    def test_engine_compute_and_save(self, test_session):
        now = datetime.now(timezone.utc)
        # Seed an agent
        agent = Agent(
            agent_id="test_agent_1",
            name="test-agent",
            provider="gemini",
            model="gemini-flash",
            config_json="{}",
            config_hash="testhash1",
            stake=10,
        )
        task = Task(
            task_id="t1",
            source="humaneval",
            prompt="Write a function",
            tests="assert True",
        )
        test_session.add_all([agent, task])
        test_session.commit()

        # Seed interaction
        inter = Interaction(
            agent_id="test_agent_1",
            task_id="t1",
            attempt=1,
            passed=True,
            tests_passed=10,
            tests_total=10,
            quality_score=1.0,
            timestamp=now,
        )
        test_session.add(inter)
        test_session.commit()

        rep_engine = ReputationEngine()
        results = rep_engine.compute_epoch_scores(test_session, epoch=1)

        assert "tracerank" in results
        assert "test_agent_1" in results["tracerank"]

        # Check DB rows
        reps = test_session.query(Reputation).filter_by(agent_id="test_agent_1", epoch=1).all()
        assert len(reps) == len(rep_engine.SUPPORTED_METHODS)
        # Check task difficulty was updated
        updated_task = test_session.get(Task, "t1")
        assert updated_task.difficulty_weight is not None
