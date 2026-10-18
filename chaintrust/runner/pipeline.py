"""
chaintrust/runner/pipeline.py
The main runner pipeline: creates jobs, dispatches to agents, grades results,
and writes Interactions to the database.

Resume support
--------------
On startup the runner queries the job_queue table for all PENDING and stale
RUNNING jobs (RUNNING jobs are assumed stale from a crashed previous run and
are reset to PENDING).  DONE jobs are never re-run.

Worker model
------------
A ThreadPoolExecutor runs up to `max_workers` concurrent jobs.  Each worker:
  1. Claims a job (sets status=RUNNING atomically).
  2. Calls the rate limiter.
  3. Calls the agent client with exponential-backoff retries.
  4. Extracts code from the response.
  5. Grades the code in the Docker sandbox.
  6. Writes an Interaction row and marks the job DONE.

The main thread polls for new pending jobs until the queue is empty.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from chaintrust.config import get_config, get_agents_config
from chaintrust.db.session import get_session, get_session_factory
from chaintrust.db.models import Agent, Task, Interaction, JobQueue, JobStatus
from chaintrust.grader.sandbox import Grader
from chaintrust.registry.agent_registry import AgentRegistry
from chaintrust.runner.clients import get_client, GenerateResult
from chaintrust.runner.extractor import extract_code
from chaintrust.runner.rate_limiter import RateLimiter, build_limiters
from chaintrust.tasks.task_bank import TaskBank

logger = logging.getLogger(__name__)

# Raw output storage directory (kept outside DB to avoid bloat)
_OUTPUT_DIR_NAME = "data/outputs"


def _sha256_hex(text: str) -> str:
    """Return SHA-256 hex of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _save_raw_output(agent_id: str, task_id: str, attempt: int, text: str) -> None:
    """Persist raw model output to disk (creates dirs as needed)."""
    safe_task = task_id.replace("/", "_")
    out_dir = Path(_OUTPUT_DIR_NAME) / agent_id / safe_task
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"attempt_{attempt}.txt").write_text(text, encoding="utf-8")


class Runner:
    """
    Orchestrates the full pipeline: job creation → agent call → grading → DB write.

    Parameters
    ----------
    agent_names:
        List of agent names to run, or ['all'] to run all enabled agents.
    task_ids:
        List of task IDs to use.  Pass None to use all tasks in the DB.
    n_tasks:
        If task_ids is None, sample this many tasks (with fixed seed).
    """

    def __init__(
        self,
        agent_names: list[str],
        task_ids: list[str] | None = None,
        n_tasks: int | None = None,
    ) -> None:
        cfg = get_config()
        self._runner_cfg    = cfg["runner"]
        self._n_attempts    = self._runner_cfg.get("attempts_per_task", 3)
        self._max_workers   = self._runner_cfg.get("max_workers", 4)
        self._strategy      = self._runner_cfg.get("code_extraction_strategy", "fence_first")
        self._poll_interval = self._runner_cfg.get("queue_poll_interval_s", 2)
        self._retry_cfg     = self._runner_cfg.get("retry", {})

        self._grader = Grader()
        self._registry = AgentRegistry()

        # Resolve agents
        if agent_names == ["all"]:
            self._agents: list[Agent] = self._registry.get_all()
        else:
            self._agents = [
                a for a in self._registry.get_all()
                if a.name in agent_names
            ]
        if not self._agents:
            raise ValueError(
                f"No agents found for names: {agent_names}. "
                "Run registration first."
            )

        # Resolve tasks
        bank = TaskBank()
        if task_ids is not None:
            with get_session() as s:
                self._tasks: list[Task] = [
                    s.query(Task).get(tid) for tid in task_ids
                    if s.query(Task).get(tid) is not None
                ]
        elif n_tasks is not None:
            self._tasks = bank.get_subset(n_tasks)
        else:
            self._tasks = bank.get_all()

        if not self._tasks:
            raise ValueError("No tasks found. Run task loading first.")

        logger.info(
            "Runner initialised: %d agents × %d tasks × %d attempts = %d jobs max",
            len(self._agents), len(self._tasks), self._n_attempts,
            len(self._agents) * len(self._tasks) * self._n_attempts,
        )

        # Build rate limiters
        all_agent_configs = get_agents_config()
        global_limits = self._runner_cfg.get("default_rate_limits", {})
        self._limiters: dict[str, RateLimiter] = build_limiters(
            all_agent_configs, global_limits
        )

        # Build agent-id → config dict for client instantiation
        self._agent_configs: dict[str, dict[str, Any]] = {}
        raw_configs = get_agents_config()
        for raw in raw_configs:
            from chaintrust.registry.agent_registry import compute_config_hash
            aid, _ = compute_config_hash(raw)
            self._agent_configs[aid] = raw

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Create pending jobs (if needed), then work through the queue until empty.
        """
        self._create_jobs()
        self._reset_stale_running()
        self._process_queue()

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def _create_jobs(self) -> None:
        """
        Insert PENDING job rows for every (agent, task, attempt) triple that
        doesn't already have a row.  Existing rows (any status) are skipped.
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        created = 0
        with get_session() as session:
            for agent in self._agents:
                for task in self._tasks:
                    for attempt in range(1, self._n_attempts + 1):
                        stmt = (
                            sqlite_insert(JobQueue)
                            .values(
                                agent_id = agent.agent_id,
                                task_id  = task.task_id,
                                attempt  = attempt,
                                status   = JobStatus.PENDING,
                            )
                            .on_conflict_do_nothing(
                                index_elements=["agent_id", "task_id", "attempt"]
                            )
                        )
                        result = session.execute(stmt)
                        created += result.rowcount
        logger.info("Job queue: %d new jobs created.", created)

    def _reset_stale_running(self) -> None:
        """
        Reset any RUNNING jobs to PENDING (they're stale from a previous crash).
        """
        with get_session() as session:
            n = (
                session.query(JobQueue)
                .filter(JobQueue.status == JobStatus.RUNNING)
                .update({"status": JobStatus.PENDING}, synchronize_session=False)
            )
            if n:
                logger.warning("Reset %d stale RUNNING jobs to PENDING.", n)

    def _claim_job(self) -> JobQueue | None:
        """
        Atomically claim one PENDING job by setting its status to RUNNING.

        Returns the claimed JobQueue row, or None if no pending jobs remain.
        """
        factory = get_session_factory()
        session = factory()
        try:
            # Lock and fetch one pending job
            job = (
                session.query(JobQueue)
                .filter(JobQueue.status == JobStatus.PENDING)
                .with_for_update()
                .first()
            )
            if job is None:
                session.close()
                return None
            job.status = JobStatus.RUNNING
            job.last_updated = datetime.now(timezone.utc)
            session.commit()
            session.refresh(job)
            return job
        except Exception:
            session.rollback()
            session.close()
            raise
        finally:
            # Don't close here; caller handles the job object
            session.close()

    # ------------------------------------------------------------------
    # Queue processor
    # ------------------------------------------------------------------

    def _process_queue(self) -> None:
        """
        Drain the job queue using a thread pool.
        """
        total_done = 0
        total_failed = 0

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {}

            def submit_more():
                """Submit as many pending jobs as the pool has free slots."""
                while len(futures) < self._max_workers:
                    job = self._claim_job()
                    if job is None:
                        break
                    future = pool.submit(self._work, job.id)
                    futures[future] = job.id

            submit_more()

            from concurrent.futures import wait, FIRST_COMPLETED

            while futures:
                done, not_done = wait(futures.keys(), timeout=self._poll_interval, return_when=FIRST_COMPLETED)
                for future in done:
                    job_id = futures.pop(future)
                    try:
                        success = future.result()
                        if success:
                            total_done += 1
                        else:
                            total_failed += 1
                    except Exception as exc:
                        logger.error("Job %d raised unexpected exception: %s", job_id, exc)
                        total_failed += 1

                # Fill pool with more jobs
                submit_more()

                # Exit if no pending jobs and no active futures
                if not futures:
                    break

        logger.info(
            "Queue drained: %d done, %d failed.",
            total_done, total_failed,
        )
        self._print_summary()

    # ------------------------------------------------------------------
    # Single job worker
    # ------------------------------------------------------------------

    def _work(self, job_id: int) -> bool:
        """
        Execute one job: call agent → grade → write Interaction.

        Returns True on success, False on final failure.
        """
        # Load the job
        with get_session() as session:
            job = session.query(JobQueue).get(job_id)
            if job is None:
                logger.error("Job %d not found.", job_id)
                return False
            agent_id = job.agent_id
            task_id  = job.task_id
            attempt  = job.attempt

        logger.info("Working job %d: agent=%s task=%s attempt=%d",
                    job_id, agent_id[:8], task_id, attempt)

        # Load agent and task from DB
        with get_session() as session:
            agent = session.query(Agent).get(agent_id)
            task  = session.query(Task).get(task_id)

        if agent is None or task is None:
            self._mark_job(job_id, JobStatus.FAILED, "Agent or task not found")
            return False

        # Build agent config for client (from our in-memory map or reconstruct)
        agent_config = self._agent_configs.get(agent_id)
        if agent_config is None:
            # Reconstruct from stored JSON
            try:
                agent_config = json.loads(agent.config_json)
            except Exception:
                self._mark_job(job_id, JobStatus.FAILED, "Cannot reconstruct agent config")
                return False

        # Rate limit
        limiter = self._limiters.get(agent.provider)
        if limiter:
            limiter.acquire()

        # Call agent with retries
        gen_result: GenerateResult | None = None
        last_error: str = ""

        max_retries = self._retry_cfg.get("max_attempts", 5)
        base_delay  = self._retry_cfg.get("base_delay_s", 2.0)
        max_delay   = self._retry_cfg.get("max_delay_s", 120.0)
        factor      = self._retry_cfg.get("backoff_factor", 2.0)

        for attempt_n in range(max_retries):
            try:
                client = get_client(agent_config)
                gen_result = client.generate(task.prompt)
                break
            except Exception as exc:
                last_error = str(exc)
                delay = min(base_delay * (factor ** attempt_n), max_delay)
                logger.warning(
                    "Agent call failed (attempt %d/%d): %s. Retrying in %.1fs …",
                    attempt_n + 1, max_retries, exc, delay,
                )
                time.sleep(delay)

        if gen_result is None:
            logger.error(
                "All %d retry attempts failed for job %d: %s",
                max_retries, job_id, last_error,
            )
            self._mark_job(job_id, JobStatus.FAILED, last_error)
            return False

        # Extract code
        code = extract_code(
            gen_result.text,
            strategy=self._strategy,
            entry_point=task.entry_point,
        )

        # Grade
        grade = self._grader.grade(
            solution_code=code,
            tests=task.tests,
            entry_point=task.entry_point,
        )

        # Store raw output
        raw_hash = _sha256_hex(gen_result.text)
        try:
            _save_raw_output(agent_id, task_id, attempt, gen_result.text)
        except Exception as exc:
            logger.warning("Could not save raw output to disk: %s", exc)

        # Write or update Interaction row
        with get_session() as session:
            existing = (
                session.query(Interaction)
                .filter_by(agent_id=agent_id, task_id=task_id, attempt=attempt)
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
                session.flush()
                interaction_id = existing.id
            else:
                interaction = Interaction(
                    agent_id         = agent_id,
                    task_id          = task_id,
                    attempt          = attempt,
                    passed           = grade.passed,
                    tests_passed     = grade.tests_passed,
                    tests_total      = grade.tests_total,
                    quality_score    = grade.quality_score,
                    runtime_ms       = grade.runtime_ms,
                    error_type       = grade.error_type,
                    stderr_excerpt   = grade.stderr_excerpt,
                    tokens_in        = gen_result.tokens_in,
                    tokens_out       = gen_result.tokens_out,
                    latency_ms       = gen_result.latency_ms,
                    raw_output_hash  = raw_hash,
                )
                session.add(interaction)
                session.flush()
                interaction_id = interaction.id

        logger.info(
            "Job %d done: passed=%s quality=%.3f runtime=%dms",
            job_id, grade.passed, grade.quality_score, grade.runtime_ms,
        )

        self._mark_job(job_id, JobStatus.DONE, interaction_id=interaction_id)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mark_job(
        self,
        job_id: int,
        status: JobStatus,
        error: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Update a job's status in the DB."""
        with get_session() as session:
            job = session.query(JobQueue).get(job_id)
            if job is None:
                return
            job.status       = status
            job.last_updated = datetime.now(timezone.utc)
            if error:
                job.error_message = str(error)[:2000]
                job.retry_count  += 1
            if interaction_id:
                job.interaction_id = interaction_id

    def _print_summary(self) -> None:
        """Print a summary table of pass rate per agent."""
        import pandas as pd

        with get_session() as session:
            rows = session.query(Interaction).all()

        if not rows:
            print("\nNo interactions in database yet.")
            return

        data = [
            {
                "agent_id":    r.agent_id,
                "passed":      int(r.passed),
                "quality":     r.quality_score,
            }
            for r in rows
        ]
        df = pd.DataFrame(data)

        # Join agent names
        with get_session() as session:
            agents = {a.agent_id: a.name for a in session.query(Agent).all()}

        df["agent_name"] = df["agent_id"].map(agents)

        summary = (
            df.groupby("agent_name")
            .agg(
                attempts    = ("passed", "count"),
                pass_count  = ("passed", "sum"),
                pass_rate   = ("passed", "mean"),
                avg_quality = ("quality", "mean"),
            )
            .sort_values("pass_rate", ascending=False)
            .reset_index()
        )

        print("\n" + "=" * 65)
        print("  ChainTrust — Pass Rate Summary")
        print("=" * 65)
        print(summary.to_string(index=False, float_format="{:.4f}".format))
        print("=" * 65)
