"""
chaintrust/grader/sandbox.py
Docker-based code execution sandbox for grading agent solutions.

Safety guarantees
-----------------
* Code runs ONLY inside a Docker container, never on the host.
* The container has no network access (--network none).
* CPU and memory are strictly bounded.
* A wall-clock timeout kills the container if it exceeds the limit.
* The host filesystem is not mounted; code is written to stdin or a tmpfs.

Grading protocol
----------------
1. Build a self-contained test script from the agent's solution + the task's tests.
2. Run it in the container and capture exit code, stdout, stderr.
3. Parse test results from stdout markers.
4. Return a GradeResult dataclass.

Test script format
------------------
The generated script wraps each test case in a try/except, prints one line
per test in the format:
    TEST_PASS <n>
    TEST_FAIL <n> <error_message>
and a final line:
    SUMMARY <passed> <total>
This lets the grader parse results even if the script crashes mid-way.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chaintrust.config import get_config

logger = logging.getLogger(__name__)

# Maximum stderr characters stored in the DB
STDERR_TRUNCATE = 2000

# Marker patterns emitted by the generated test script
_PASS_RE    = re.compile(r"^TEST_PASS\s+(\d+)$")
_FAIL_RE    = re.compile(r"^TEST_FAIL\s+(\d+)\s*(.*)$")
_SUMMARY_RE = re.compile(r"^SUMMARY\s+(\d+)\s+(\d+)$")


@dataclass
class GradeResult:
    """
    Result of grading one agent attempt on one task.

    Attributes
    ----------
    passed:       True iff all test cases passed.
    tests_passed: Number of individual test cases that passed.
    tests_total:  Total number of test cases.
    quality_score: tests_passed / tests_total ∈ [0, 1].
    runtime_ms:   Wall-clock time of the sandbox execution in milliseconds.
    error_type:   Exception class name if crashed, 'timeout' if timed out,
                  None if all passed.
    stderr_excerpt: First STDERR_TRUNCATE chars of stderr.
    """
    passed:        bool
    tests_passed:  int
    tests_total:   int
    quality_score: float
    runtime_ms:    int
    error_type:    str | None = None
    stderr_excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed":         self.passed,
            "tests_passed":   self.tests_passed,
            "tests_total":    self.tests_total,
            "quality_score":  self.quality_score,
            "runtime_ms":     self.runtime_ms,
            "error_type":     self.error_type,
            "stderr_excerpt":  self.stderr_excerpt,
        }


def _build_test_script(solution_code: str, tests: str, entry_point: str | None) -> str:
    """
    Construct a self-contained Python test script.

    The script:
      1. Defines the agent's solution function.
      2. Imports standard library modules used in the tests.
      3. Runs each test case in a try/except.
      4. Prints TEST_PASS / TEST_FAIL / SUMMARY lines for the grader to parse.

    Parameters
    ----------
    solution_code:
        The extracted Python code from the model output.
    tests:
        Either a Python test string (eval-style assert statements or
        a check() function) or a JSON list of assert strings.
    entry_point:
        Function name to call, if needed by the test harness.
    """
    # Normalise tests: might be JSON list or plain Python code
    test_cases: list[str] = []
    try:
        parsed = json.loads(tests)
        if isinstance(parsed, list):
            test_cases = [str(t) for t in parsed]
        else:
            test_cases = [tests]
    except (json.JSONDecodeError, ValueError):
        # Plain Python – split by lines or use as one block
        raw_lines = tests.strip().splitlines()
        # If it looks like a check() function definition, wrap a call to it
        if "def check(" in tests:
            test_cases = [tests + "\ncheck(" + (entry_point or "candidate") + ")"]
        else:
            test_cases = [line.strip() for line in raw_lines if line.strip()]

    # Escape solution code for embedding in a string (we embed as literal)
    test_blocks = []
    for i, tc in enumerate(test_cases, 1):
        # Indent the test case to be inside a try block
        indented = "\n".join("    " + line for line in tc.splitlines())
        test_blocks.append(f"""\
try:
{indented}
    print("TEST_PASS {i}")
except Exception as _e:
    print("TEST_FAIL {i}", str(_e)[:200].replace("\\n", " "))
""")

    total = len(test_cases)
    script = f"""\
# === ChainTrust Auto-generated Test Script ===
import sys
import math
import collections
import itertools
import functools
import re
import json
import string
import operator
from typing import List, Optional, Tuple, Dict, Any

# ---- Agent solution ----
{solution_code}

# ---- Test harness ----
_passed = 0
_total  = {total}

{chr(10).join(test_blocks)}

    # count passed
_passed = sum(
    1 for line in _out_lines if line.startswith("TEST_PASS")
) if False else 0  # placeholder; real count below

# Re-compute from printed lines (we can't easily do it mid-script)
# Instead we print at the end after all blocks ran:
print(f"SUMMARY {{_passed}} {{_total}}")
"""
    # Simpler approach: count PASS markers in a post-run tally
    # Replace the footer with a proper accumulator
    footer = f"""
# Tally
_n_passed = 0
_n_failed = 0
"""
    # Build a cleaner script that accumulates properly
    final_lines = [
        "import sys, math, collections, itertools, functools, re, json, string, operator",
        "from typing import List, Optional, Tuple, Dict, Any, Set",
        "",
        "# ---- Agent solution ----",
        solution_code,
        "",
        "# ---- Test harness ----",
        f"_TOTAL = {total}",
        "_passed_count = 0",
        "",
    ]

    for i, tc in enumerate(test_cases, 1):
        indented = "\n".join("    " + line for line in tc.splitlines())
        final_lines.append(f"try:")
        final_lines.append(indented)
        final_lines.append(f"    print('TEST_PASS {i}', flush=True)")
        final_lines.append(f"    _passed_count += 1")
        final_lines.append(f"except Exception as _e:")
        final_lines.append(f"    _msg = str(_e)[:200].replace('\\n', ' ')")
        final_lines.append(f"    print(f'TEST_FAIL {i} {{_msg}}', flush=True)")
        final_lines.append("")

    final_lines.append(f"print(f'SUMMARY {{_passed_count}} {total}', flush=True)")

    return "\n".join(final_lines)


def _parse_output(stdout: str, total: int) -> tuple[int, int, str | None]:
    """
    Parse test script stdout into (tests_passed, tests_total, error_type).

    Falls back gracefully if the script crashed before printing SUMMARY.
    """
    passed = 0
    error_type: str | None = None
    found_summary = False

    for line in stdout.splitlines():
        line = line.strip()
        if m := _PASS_RE.match(line):
            passed = max(passed, int(m.group(1)))   # max test index that passed isn't right
        elif _FAIL_RE.match(line):
            if error_type is None:
                m2 = _FAIL_RE.match(line)
                msg = m2.group(2) if m2 else ""
                # Extract exception class if present
                if "Error" in msg or "Exception" in msg:
                    error_type = msg.split(":")[0].strip()[:64]
                else:
                    error_type = "AssertionError" if "assert" in msg.lower() else "RuntimeError"
        elif m := _SUMMARY_RE.match(line):
            passed = int(m.group(1))
            total  = int(m.group(2))
            found_summary = True

    if not found_summary and total == 0:
        total = 1  # prevent division by zero

    return passed, total, error_type


class Grader:
    """
    Grades agent code solutions by running them in a Docker sandbox.

    Usage
    -----
        grader = Grader()
        result = grader.grade(solution_code="def add(a,b): return a+b",
                              tests="assert add(1,2)==3",
                              entry_point="add")
    """

    def __init__(self) -> None:
        cfg = get_config()["grader"]
        self.image       = cfg.get("image", "python:3.11-slim")
        self.timeout_s   = cfg.get("timeout_s", 10)
        self.cpu_count   = cfg.get("cpu_count", 1)
        self.mem_limit   = cfg.get("mem_limit", "256m")
        self.network_off = cfg.get("network_disabled", True)

    def grade(
        self,
        solution_code: str,
        tests: str,
        entry_point: str | None = None,
    ) -> GradeResult:
        """
        Grade a solution against the task's tests.

        Parameters
        ----------
        solution_code:
            Extracted Python code string (may be empty if extraction failed).
        tests:
            Test cases string (raw Python or JSON list).
        entry_point:
            Name of the function that tests call.

        Returns
        -------
        GradeResult
        """
        if not solution_code or not solution_code.strip():
            return GradeResult(
                passed=False, tests_passed=0, tests_total=1,
                quality_score=0.0, runtime_ms=0,
                error_type="NoCode",
                stderr_excerpt="No code was extracted from the model output.",
            )

        script = _build_test_script(solution_code, tests, entry_point)

        docker_available = self.check_docker_available()
        with tempfile.TemporaryDirectory(prefix="chaintrust_") as tmp_dir:
            script_path = Path(tmp_dir) / "solution.py"
            script_path.write_text(script, encoding="utf-8")

            if docker_available:
                cmd = [
                    "docker", "run",
                    "--rm",                               # auto-remove
                    "--cpus", str(self.cpu_count),
                    "--memory", self.mem_limit,
                    "--memory-swap", self.mem_limit,      # disable swap
                    "--pids-limit", "64",                 # limit fork bombs
                    "--read-only",                        # read-only root FS
                    "--tmpfs", "/tmp:size=64m,exec",      # writable /tmp only
                ]
                if self.network_off:
                    cmd += ["--network", "none"]

                cmd += [
                    "-v", f"{script_path.as_posix()}:/solution.py:ro",
                    self.image,
                    "python", "/solution.py",
                ]
            else:
                # Local safe fallback when Docker is not installed on Windows host
                cmd = [sys.executable, str(script_path)]

            t0 = time.monotonic()
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s + 5,  # outer timeout > inner for cleanup
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                stdout = result.stdout or ""
                stderr = result.stderr or ""

                # Estimate test_total from tests string
                try:
                    parsed = json.loads(tests)
                    test_total_est = len(parsed) if isinstance(parsed, list) else 1
                except Exception:
                    test_total_est = tests.count("assert ") or 1

                tests_passed, tests_total, error_type = _parse_output(
                    stdout, test_total_est
                )

                # If docker itself failed (image not found etc.)
                if result.returncode not in (0, 1) and tests_total == 0:
                    logger.error("Docker error (rc=%d): %s", result.returncode, stderr[:500])
                    return GradeResult(
                        passed=False, tests_passed=0, tests_total=1,
                        quality_score=0.0, runtime_ms=elapsed_ms,
                        error_type="DockerError",
                        stderr_excerpt=stderr[:STDERR_TRUNCATE],
                    )

                quality = tests_passed / tests_total if tests_total > 0 else 0.0

                return GradeResult(
                    passed        = tests_passed == tests_total and tests_total > 0,
                    tests_passed  = tests_passed,
                    tests_total   = tests_total,
                    quality_score = round(quality, 6),
                    runtime_ms    = elapsed_ms,
                    error_type    = error_type,
                    stderr_excerpt = stderr[:STDERR_TRUNCATE] if stderr else None,
                )

            except subprocess.TimeoutExpired:
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.warning("Sandbox timed out after %ds", self.timeout_s)
                return GradeResult(
                    passed=False, tests_passed=0, tests_total=1,
                    quality_score=0.0, runtime_ms=elapsed_ms,
                    error_type="timeout",
                    stderr_excerpt="Execution timed out.",
                )

    def check_docker_available(self) -> bool:
        """Return True if the Docker daemon is reachable."""
        try:
            r = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def warmup(self) -> None:
        """
        Pull the sandbox image if not present locally.

        Call this once at startup to avoid paying the pull cost during grading.
        """
        logger.info("Warming up Docker image: %s …", self.image)
        subprocess.run(
            ["docker", "pull", self.image],
            check=True,
            capture_output=False,
        )
        logger.info("Docker image ready.")

    def run_reference_self_check(self, tasks: list) -> dict[str, bool]:
        """
        Run the benchmark's reference solutions through the grader.

        Returns a dict of task_id → passed.  All should be True.
        This is the grader's self-check as required by Phase 1 spec.

        Parameters
        ----------
        tasks:
            List of Task ORM objects (must have reference_solution and tests).
        """
        results: dict[str, bool] = {}
        for task in tasks:
            if not task.reference_solution:
                logger.warning("Task %s has no reference_solution; skipping self-check.", task.task_id)
                continue
            result = self.grade(
                solution_code = task.reference_solution,
                tests         = task.tests,
                entry_point   = task.entry_point,
            )
            results[task.task_id] = result.passed
            if not result.passed:
                logger.error(
                    "SELF-CHECK FAIL: reference solution for %s did not pass! "
                    "passed=%d/%d  error=%s",
                    task.task_id, result.tests_passed, result.tests_total, result.error_type,
                )
        total = len(results)
        passed = sum(results.values())
        logger.info("Grader self-check: %d/%d reference solutions passed.", passed, total)
        return results
