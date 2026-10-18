"""
chaintrust/tasks/task_bank.py
Loads HumanEval and MBPP (EvalPlus variants when available) into the tasks table.

Loader design
-------------
Each loader is a standalone function `_load_<source>(subset_size, data_dir)` that
returns a list of Task ORM objects.  Adding a new benchmark means adding a new
loader and registering it in LOADERS.  The TaskBank.load_all() method calls
all registered loaders in order.

EvalPlus
--------
EvalPlus extends HumanEval (→ HumanEval+) and MBPP (→ MBPP+) with more
rigorous test cases.  We prefer the EvalPlus version if the `evalplus` Python
package is installed.  If not, we fall back to the original datasets via the
`datasets` library (Hugging Face).

Task ID scheme
--------------
  humaneval/<original_task_id>   e.g.  humaneval/HumanEval/0
  mbpp/<original_task_id>        e.g.  mbpp/11
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from chaintrust.config import get_config
from chaintrust.db.session import get_session
from chaintrust.db.models import Task, TaskSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_id(source: str, original_id: Any) -> str:
    return f"{source}/{original_id}"


def _tests_to_str(tests: Any) -> str:
    """Normalise test cases to a single JSON string for storage."""
    if isinstance(tests, str):
        return tests
    return json.dumps(tests, ensure_ascii=False)


# ---------------------------------------------------------------------------
# HumanEval loader
# ---------------------------------------------------------------------------

def _load_humaneval(subset_size: int | None, data_dir: Path) -> list[Task]:
    """
    Load HumanEval (or HumanEval+ via EvalPlus) tasks.

    Returns a list of Task objects (not yet in the DB).
    """
    tasks: list[Task] = []

    # --- Try EvalPlus first ------------------------------------------------
    try:
        from evalplus.data import get_human_eval_plus  # type: ignore
        logger.info("Loading HumanEval+ via evalplus …")
        dataset = get_human_eval_plus()
        # dataset is a dict: task_id -> {prompt, entry_point, test, canonical_solution, ...}
        items = list(dataset.items())
        if subset_size is not None:
            items = items[:subset_size]

        for original_id, item in items:
            task_id = _make_task_id("humaneval", original_id)
            tasks.append(Task(
                task_id    = task_id,
                source     = TaskSource.HUMANEVAL,
                prompt     = item["prompt"],
                entry_point= item.get("entry_point"),
                tests      = _tests_to_str(item.get("test", item.get("tests", ""))),
                reference_solution = item.get("canonical_solution"),
            ))
        return tasks

    except ImportError:
        logger.warning("evalplus not installed; falling back to HuggingFace datasets for HumanEval.")

    # --- Fallback: HuggingFace datasets -------------------------------------
    try:
        from datasets import load_dataset  # type: ignore
        logger.info("Loading HumanEval from HuggingFace datasets …")
        ds = load_dataset("openai_humaneval", split="test", trust_remote_code=True)

        items = list(ds)
        if subset_size is not None:
            items = items[:subset_size]

        for item in items:
            task_id = _make_task_id("humaneval", item["task_id"])
            tasks.append(Task(
                task_id    = task_id,
                source     = TaskSource.HUMANEVAL,
                prompt     = item["prompt"],
                entry_point= item.get("entry_point"),
                tests      = _tests_to_str(item.get("test", "")),
                reference_solution = item.get("canonical_solution"),
            ))
        return tasks

    except Exception as exc:
        logger.error("Failed to load HumanEval: %s", exc)
        raise


# ---------------------------------------------------------------------------
# MBPP loader
# ---------------------------------------------------------------------------

def _load_mbpp(subset_size: int | None, data_dir: Path) -> list[Task]:
    """
    Load MBPP (or MBPP+ via EvalPlus) tasks.

    MBPP test cases are Python assert statements stored as a list of strings.
    We join them with newlines for the grader.
    """
    tasks: list[Task] = []

    # --- Try EvalPlus first ------------------------------------------------
    try:
        from evalplus.data import get_mbpp_plus  # type: ignore
        logger.info("Loading MBPP+ via evalplus …")
        dataset = get_mbpp_plus()
        items = list(dataset.items())
        if subset_size is not None:
            items = items[:subset_size]

        for original_id, item in items:
            task_id = _make_task_id("mbpp", original_id)
            # Combine task_id prompt and the function signature
            prompt = item.get("prompt", item.get("text", ""))
            tests  = _tests_to_str(item.get("test", item.get("test_list", [])))
            tasks.append(Task(
                task_id    = task_id,
                source     = TaskSource.MBPP,
                prompt     = prompt,
                entry_point= item.get("entry_point", item.get("code", "").split("def ")[1].split("(")[0].strip()
                             if "def " in item.get("code", "") else None),
                tests      = tests,
                reference_solution = item.get("code"),
            ))
        return tasks

    except ImportError:
        logger.warning("evalplus not installed; falling back to HuggingFace datasets for MBPP.")

    # --- Fallback: HuggingFace datasets -------------------------------------
    try:
        from datasets import load_dataset  # type: ignore
        logger.info("Loading MBPP from HuggingFace datasets …")
        # mbpp has splits: train, validation, test, prompt
        ds = load_dataset("mbpp", "sanitized", split="test", trust_remote_code=True)

        items = list(ds)
        if subset_size is not None:
            items = items[:subset_size]

        for item in items:
            task_id = _make_task_id("mbpp", item["task_id"])
            test_list = item.get("test_list", [])
            tests_str = "\n".join(test_list) if isinstance(test_list, list) else str(test_list)

            # Extract entry point from reference code
            entry_point = None
            code = item.get("code", "")
            if "def " in code:
                try:
                    entry_point = code.split("def ")[1].split("(")[0].strip()
                except Exception:
                    pass

            tasks.append(Task(
                task_id    = task_id,
                source     = TaskSource.MBPP,
                prompt     = item.get("text", ""),
                entry_point= entry_point,
                tests      = tests_str,
                reference_solution = code,
            ))
        return tasks

    except Exception as exc:
        logger.error("Failed to load MBPP: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Extension point: LiveCodeBench
# ---------------------------------------------------------------------------

def _load_livecodebench(subset_size: int | None, data_dir: Path) -> list[Task]:
    """
    Placeholder loader for LiveCodeBench (Phase 4+).

    Raises NotImplementedError until implemented.
    """
    raise NotImplementedError(
        "LiveCodeBench loader is not yet implemented. "
        "Add it in chaintrust/tasks/task_bank.py::_load_livecodebench()"
    )


# ---------------------------------------------------------------------------
# Loader registry — add new benchmarks here
# ---------------------------------------------------------------------------

LOADERS: dict[str, Any] = {
    "humaneval":      _load_humaneval,
    "mbpp":           _load_mbpp,
    "livecodebench":  _load_livecodebench,
}


# ---------------------------------------------------------------------------
# TaskBank
# ---------------------------------------------------------------------------

class TaskBank:
    """
    Manages loading and retrieval of benchmark tasks.

    Usage
    -----
        bank = TaskBank()
        tasks = bank.load_all()        # loads & upserts all configured sources
        tasks = bank.get_all()         # reads from DB
        tasks = bank.get_subset(50)    # random 50 (reproducible via seed)
    """

    def load_all(self) -> list[Task]:
        """
        Load all configured task sources and upsert them into the DB.

        Returns the list of Task ORM objects that were processed.
        Existing tasks (same task_id) are left untouched.
        """
        cfg = get_config()
        task_cfg  = cfg["tasks"]
        sources: list[str] = task_cfg.get("sources", ["humaneval", "mbpp"])
        subset_size: int | None = task_cfg.get("subset_size", 100)
        data_dir = Path(cfg.get("tasks", {}).get("data_dir", "data/tasks"))
        data_dir.mkdir(parents=True, exist_ok=True)

        all_tasks: list[Task] = []

        for source in sources:
            loader = LOADERS.get(source)
            if loader is None:
                logger.warning("Unknown task source '%s'; skipping.", source)
                continue

            logger.info("Loading source: %s (subset=%s)", source, subset_size)
            try:
                tasks = loader(subset_size, data_dir)
                logger.info("  → %d tasks loaded from %s", len(tasks), source)
                self._upsert_tasks(tasks)
                all_tasks.extend(tasks)
            except NotImplementedError as exc:
                logger.warning("Source '%s' skipped: %s", source, exc)
            except Exception as exc:
                logger.error("Failed to load source '%s': %s", source, exc)
                raise

        logger.info("Total tasks loaded: %d", len(all_tasks))
        return all_tasks

    def _upsert_tasks(self, tasks: list[Task]) -> None:
        """Insert tasks, ignoring conflicts (existing task_id wins)."""
        with get_session() as session:
            for task in tasks:
                stmt = (
                    sqlite_insert(Task)
                    .values(
                        task_id            = task.task_id,
                        source             = task.source,
                        prompt             = task.prompt,
                        entry_point        = task.entry_point,
                        tests              = task.tests,
                        reference_solution = task.reference_solution,
                    )
                    .on_conflict_do_nothing(index_elements=["task_id"])
                )
                session.execute(stmt)

    def get_all(self) -> list[Task]:
        """Return all tasks from the database."""
        with get_session() as session:
            return session.query(Task).all()

    def get_subset(self, n: int, seed: int | None = None) -> list[Task]:
        """
        Return a reproducible random subset of n tasks.

        Parameters
        ----------
        n:
            Number of tasks to return.
        seed:
            Random seed (defaults to config.project.random_seed).
        """
        import random

        cfg = get_config()
        if seed is None:
            seed = cfg.get("project", {}).get("random_seed", 42)

        all_tasks = self.get_all()
        rng = random.Random(seed)
        sample = rng.sample(all_tasks, min(n, len(all_tasks)))
        return sample

    def get_by_id(self, task_id: str) -> Task | None:
        """Return a Task by its task_id, or None."""
        with get_session() as session:
            return session.query(Task).get(task_id)

    def count(self) -> int:
        """Return total number of tasks in the DB."""
        with get_session() as session:
            return session.query(Task).count()
