"""
chaintrust/db/models.py
SQLAlchemy ORM models for the entire ChainTrust schema.

Design notes
------------
* All primary keys are meaningful strings (agent_id, task_id) or
  auto-increment integers — never UUIDs — so they're easy to inspect in SQLite.
* `config_hash` on Agent is SHA-256 of the canonical JSON of the agent config.
  It is computed by the registry, not stored in agents.yaml.
* `raw_output_hash` on Interaction is SHA-256 of the full raw model output so
  we can detect tampering without storing the (potentially large) full text.
* `difficulty_weight` is stored per-interaction row so that the verifier can
  reproduce reputation scores without re-running the dataset.
* JobQueue is the persistent task queue used by the runner for resume support.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared base class for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Enum types
# ---------------------------------------------------------------------------

class JobStatus(str, enum.Enum):
    """Status values for the persistent job queue."""
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    SKIPPED  = "skipped"   # e.g. agent disabled mid-run


class TaskSource(str, enum.Enum):
    """Which benchmark a task came from."""
    HUMANEVAL     = "humaneval"
    MBPP          = "mbpp"
    LIVECODEBENCH = "livecodebench"   # extension point for Phase 4+


# ---------------------------------------------------------------------------
# Core tables
# ---------------------------------------------------------------------------

class Agent(Base):
    """
    One registered agent instance.

    An 'agent' is a *specific configuration* of a model: same model with
    different system_prompt or temperature is a different agent.  This lets
    us run ablations and Sybil experiments cleanly.
    """
    __tablename__ = "agents"

    agent_id    = Column(String(64),  primary_key=True,
                         doc="SHA-256 of canonical config JSON (first 16 bytes, hex)")
    name        = Column(String(128), nullable=False, unique=True,
                         doc="Human-readable label from agents.yaml")
    provider    = Column(String(32),  nullable=False,
                         doc="API provider: gemini | groq | openrouter | ollama")
    model       = Column(String(128), nullable=False,
                         doc="Exact model ID as used by the provider API")
    config_json = Column(Text,        nullable=False,
                         doc="Full canonical JSON of the agent config")
    config_hash = Column(String(64),  nullable=False, unique=True,
                         doc="SHA-256 hex of config_json for integrity checking")
    stake       = Column(Integer,     nullable=False, default=0,
                         doc="Integer stake used in TraceRank rater-trust weighting")
    created_at  = Column(DateTime(timezone=True), nullable=False,
                         default=lambda: datetime.now(timezone.utc))

    # Relationships
    interactions = relationship("Interaction", back_populates="agent",
                                cascade="all, delete-orphan")
    reputation_rows = relationship("Reputation", back_populates="agent",
                                   cascade="all, delete-orphan")
    anchor_rows  = relationship("Anchor",      back_populates="agent",
                                cascade="all, delete-orphan")
    job_queue    = relationship("JobQueue",    back_populates="agent",
                                cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Agent {self.name!r} ({self.provider}/{self.model})>"


class Task(Base):
    """
    One benchmark task (coding problem).

    `entry_point` is the function name the grader must call.
    `tests`       is the raw test code / test cases string from the benchmark.
    `difficulty_weight` starts as NULL and is filled by the reputation engine
    after enough interactions exist to compute it from pass-rate data.
    """
    __tablename__ = "tasks"

    task_id     = Column(String(64),  primary_key=True,
                         doc="Stable ID: <source>/<original_id>, e.g. humaneval/HumanEval_0")
    source      = Column(Enum(TaskSource), nullable=False)
    prompt      = Column(Text,        nullable=False,
                         doc="Full task description / docstring shown to the agent")
    entry_point = Column(String(128), nullable=True,
                         doc="Name of the function the solution must implement")
    tests       = Column(Text,        nullable=False,
                         doc="Test harness code or JSON list of test cases")
    reference_solution = Column(Text, nullable=True,
                         doc="Ground-truth solution (used in grader self-check)")
    difficulty_weight  = Column(Float, nullable=True,
                         doc="d_t = 1 - pass_fraction, set by reputation engine")
    created_at  = Column(DateTime(timezone=True), nullable=False,
                         default=lambda: datetime.now(timezone.utc))

    interactions = relationship("Interaction", back_populates="task",
                                cascade="all, delete-orphan")
    job_queue    = relationship("JobQueue",    back_populates="task",
                                cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Task {self.task_id!r} ({self.source})>"


class Interaction(Base):
    """
    One graded agent attempt at one task.

    This is the atomic unit of the entire pipeline:
    every other table (Reputation, Anchor) is derived from these rows.

    raw_output_hash  – SHA-256 of the full raw model output (hex).
                       The raw text itself is NOT stored here to keep the DB
                       small; it lives in the file-system cache under
                       data/outputs/<agent_id>/<task_id>/<attempt>.txt.
    quality_score    – tests_passed / tests_total ∈ [0, 1].
    difficulty_weight – snapshot of the task's difficulty at the time this
                        interaction was used in a reputation computation.
                        NULL until first reputation run.
    """
    __tablename__ = "interactions"

    id               = Column(Integer,     primary_key=True, autoincrement=True)
    agent_id         = Column(String(64),  ForeignKey("agents.agent_id"), nullable=False)
    task_id          = Column(String(64),  ForeignKey("tasks.task_id"),   nullable=False)
    attempt          = Column(Integer,     nullable=False,
                              doc="1-indexed attempt number (1..N)")

    # Grading results
    passed           = Column(Boolean,     nullable=False,
                              doc="True iff all test cases passed")
    tests_passed     = Column(Integer,     nullable=False)
    tests_total      = Column(Integer,     nullable=False)
    quality_score    = Column(Float,       nullable=False,
                              doc="tests_passed / tests_total ∈ [0, 1]")
    runtime_ms       = Column(Integer,     nullable=True,
                              doc="Wall-clock time for sandbox execution in ms")
    error_type       = Column(String(64),  nullable=True,
                              doc="Exception class or 'timeout' if sandbox timed out")
    stderr_excerpt   = Column(Text,        nullable=True,
                              doc="First 2000 chars of stderr from sandbox")

    # Token usage
    tokens_in        = Column(Integer,     nullable=True)
    tokens_out       = Column(Integer,     nullable=True)
    latency_ms       = Column(Integer,     nullable=True,
                              doc="Wall-clock time for the API call in ms")

    # Reputation-engine snapshot (filled during scoring)
    difficulty_weight = Column(Float,      nullable=True)

    # Audit trail
    raw_output_hash  = Column(String(64),  nullable=True,
                              doc="SHA-256 hex of the raw model output string")
    timestamp        = Column(DateTime(timezone=True), nullable=False,
                              default=lambda: datetime.now(timezone.utc),
                              doc="UTC timestamp when the interaction was recorded")

    # Relationships
    agent = relationship("Agent", back_populates="interactions")
    task  = relationship("Task",  back_populates="interactions")

    __table_args__ = (
        UniqueConstraint("agent_id", "task_id", "attempt",
                         name="uq_interaction_agent_task_attempt"),
        CheckConstraint("attempt >= 1",         name="ck_attempt_positive"),
        CheckConstraint("quality_score >= 0.0 AND quality_score <= 1.0",
                        name="ck_quality_score_range"),
    )

    def __repr__(self) -> str:
        return (f"<Interaction agent={self.agent_id!r} task={self.task_id!r} "
                f"attempt={self.attempt} passed={self.passed}>")


# ---------------------------------------------------------------------------
# Reputation table
# ---------------------------------------------------------------------------

class Reputation(Base):
    """
    Computed reputation score per agent, per epoch, per scoring method.

    One row is written every time a scoring method is run.  Storing all
    methods lets us compare them side-by-side (Phase 2) and lets the verifier
    reproduce the claimed score from the bundle.
    """
    __tablename__ = "reputation"

    id          = Column(Integer,    primary_key=True, autoincrement=True)
    agent_id    = Column(String(64), ForeignKey("agents.agent_id"), nullable=False)
    epoch       = Column(Integer,    nullable=False,
                         doc="Epoch number (interactions-based or daily)")
    method      = Column(String(64), nullable=False,
                         doc="Scoring method: simple_avg | weighted | pagerank | "
                             "eigentrust | tracerank")
    score       = Column(Float,      nullable=False,
                         doc="Rounded to config.reputation.rounding_decimals decimals")
    computed_at = Column(DateTime(timezone=True), nullable=False,
                         default=lambda: datetime.now(timezone.utc))

    agent = relationship("Agent", back_populates="reputation_rows")

    __table_args__ = (
        UniqueConstraint("agent_id", "epoch", "method",
                         name="uq_reputation_agent_epoch_method"),
    )

    def __repr__(self) -> str:
        return (f"<Reputation agent={self.agent_id!r} epoch={self.epoch} "
                f"method={self.method!r} score={self.score:.6f}>")


# ---------------------------------------------------------------------------
# Blockchain anchor table
# ---------------------------------------------------------------------------

class Anchor(Base):
    """
    On-chain anchor for one agent's Merkle root at one epoch.

    merkle_root  – the root of the Merkle tree built over that agent's
                   interactions in the given epoch (keccak256, hex).
    score_hash   – keccak256(agent_id || epoch || method || score_bytes)
                   so the claimed score is committed to on-chain.
    tx_hash      – Ethereum transaction hash (NULL until confirmed).
    block_number – block number containing the anchor tx.
    """
    __tablename__ = "anchors"

    id           = Column(Integer,    primary_key=True, autoincrement=True)
    agent_id     = Column(String(64), ForeignKey("agents.agent_id"), nullable=False)
    epoch        = Column(Integer,    nullable=False)
    merkle_root  = Column(String(66), nullable=False,
                          doc="0x-prefixed keccak256 hex of Merkle root")
    score_hash   = Column(String(66), nullable=True,
                          doc="0x-prefixed keccak256 of the score commitment")
    tx_hash      = Column(String(66), nullable=True,
                          doc="Ethereum tx hash (NULL until mined)")
    block_number = Column(BigInteger, nullable=True)
    anchored_at  = Column(DateTime(timezone=True), nullable=True,
                          doc="UTC timestamp of block inclusion")

    agent = relationship("Agent", back_populates="anchor_rows")

    __table_args__ = (
        UniqueConstraint("agent_id", "epoch",
                         name="uq_anchor_agent_epoch"),
    )

    def __repr__(self) -> str:
        return (f"<Anchor agent={self.agent_id!r} epoch={self.epoch} "
                f"root={self.merkle_root!r}>")


# ---------------------------------------------------------------------------
# Persistent job queue
# ---------------------------------------------------------------------------

class JobQueue(Base):
    """
    Persistent job queue for the runner (resume support).

    Each row represents one (agent, task, attempt) unit of work.
    The runner writes PENDING rows at startup (skipping any already DONE/FAILED),
    then workers pick rows up atomically by setting status=RUNNING.

    On restart the runner finds all RUNNING rows (stale), resets them to PENDING,
    and continues.  DONE rows are never retried.
    """
    __tablename__ = "job_queue"

    id          = Column(Integer,    primary_key=True, autoincrement=True)
    agent_id    = Column(String(64), ForeignKey("agents.agent_id"), nullable=False)
    task_id     = Column(String(64), ForeignKey("tasks.task_id"),   nullable=False)
    attempt     = Column(Integer,    nullable=False)
    status      = Column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)

    # Populated on completion / failure
    interaction_id = Column(Integer, ForeignKey("interactions.id"), nullable=True,
                            doc="Foreign key to the resulting Interaction row, if DONE")
    error_message  = Column(Text,    nullable=True,
                            doc="Last error if status=FAILED")
    retry_count    = Column(Integer, nullable=False, default=0)
    last_updated   = Column(DateTime(timezone=True), nullable=False,
                            default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))
    created_at     = Column(DateTime(timezone=True), nullable=False,
                            default=lambda: datetime.now(timezone.utc))

    agent = relationship("Agent", back_populates="job_queue")
    task  = relationship("Task",  back_populates="job_queue")

    __table_args__ = (
        UniqueConstraint("agent_id", "task_id", "attempt",
                         name="uq_job_agent_task_attempt"),
        CheckConstraint("attempt >= 1",    name="ck_job_attempt_positive"),
        CheckConstraint("retry_count >= 0",name="ck_retry_count_nonneg"),
    )

    def __repr__(self) -> str:
        return (f"<Job agent={self.agent_id!r} task={self.task_id!r} "
                f"attempt={self.attempt} status={self.status}>")
