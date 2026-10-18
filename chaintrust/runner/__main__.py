"""
chaintrust/runner/__main__.py
CLI entrypoint:  python -m chaintrust.runner [options]

Examples
--------
    # Run all enabled agents on 20 randomly sampled tasks
    python -m chaintrust.runner --agents all --tasks 20

    # Run specific agents on specific tasks
    python -m chaintrust.runner --agents gemini-flash-default llama3-groq-default --tasks 50

    # Skip DB init (if already initialised)
    python -m chaintrust.runner --agents all --tasks 20 --no-init

    # Run grader self-check (reference solutions) before starting
    python -m chaintrust.runner --agents all --tasks 20 --self-check
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m chaintrust.runner",
        description="ChainTrust Phase 1 runner: run agents on benchmark tasks.",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["all"],
        metavar="AGENT_NAME",
        help='Agent names to run, or "all" for all enabled agents.',
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=None,
        metavar="N",
        help="Number of tasks to sample (default: all tasks in DB).",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="Skip database initialisation and task loading.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run grader self-check (reference solutions) before the main run.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Override max_workers from config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Import here (after logging is configured by chaintrust/__init__.py)
    from chaintrust.db.session import init_db
    from chaintrust.registry.agent_registry import AgentRegistry
    from chaintrust.tasks.task_bank import TaskBank
    from chaintrust.grader.sandbox import Grader
    from chaintrust.runner.pipeline import Runner

    # 1. Database setup
    if not args.no_init:
        logger.info("Initialising database …")
        init_db()

        logger.info("Registering agents from agents.yaml …")
        registry = AgentRegistry()
        agents = registry.register_all()
        logger.info("Registered %d agents.", len(agents))

        logger.info("Loading tasks …")
        bank = TaskBank()
        bank.load_all()
        logger.info("Task bank: %d tasks.", bank.count())
    else:
        logger.info("Skipping init (--no-init).")

    # 2. Grader self-check (optional)
    if args.self_check:
        grader = Grader()
        if not grader.check_docker_available():
            logger.error("Docker daemon is not reachable. Cannot run grader self-check.")
            return 1
        from chaintrust.tasks.task_bank import TaskBank
        bank = TaskBank()
        sample = bank.get_subset(10)
        logger.info("Running grader self-check on %d reference solutions …", len(sample))
        grader.warmup()
        results = grader.run_reference_self_check(sample)
        failures = [tid for tid, ok in results.items() if not ok]
        if failures:
            logger.error("Self-check FAILED for %d tasks: %s", len(failures), failures)
            return 1
        logger.info("Self-check passed for all reference solutions.")

    # 3. Check Docker is available for grading
    grader = Grader()
    if not grader.check_docker_available():
        logger.warning(
            "Docker daemon not reachable. Grading will fail. "
            "Start Docker and re-run, or check your Docker installation."
        )

    # 4. Patch max_workers if overridden
    if args.workers is not None:
        from chaintrust.config import get_config
        get_config()["runner"]["max_workers"] = args.workers

    # 5. Run the pipeline
    runner = Runner(
        agent_names=args.agents,
        n_tasks=args.tasks,
    )
    runner.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
