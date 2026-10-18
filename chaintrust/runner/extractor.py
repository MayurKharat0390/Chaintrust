"""
chaintrust/runner/extractor.py
Robust code extraction from free-form model outputs.

Strategy: fence_first → any_block → heuristic (configurable).

fence_first (default)
---------------------
Look for ```python ... ``` or ``` ... ``` fenced blocks.
Take the FIRST fenced block that contains a function definition or
resembles Python code.  If multiple fenced blocks exist, we take the
longest one (most likely the full solution rather than an inline snippet).

any_block
---------
Same as fence_first but also accepts non-Python-labeled fences (```java etc.)
and extracts the block if its content parses as Python.

heuristic
---------
If no fence is found, look for lines that start with 'def ' or common
Python patterns and extract from there to the end of the response.

All strategies strip trailing prose after the code block.
"""

from __future__ import annotations

import ast
import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

# Regex for fenced code blocks.  Group 1 = optional language tag, Group 2 = code.
_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9_+-]*)?\s*\n(?P<code>.*?)```",
    re.DOTALL,
)

ExtractionStrategy = Literal["fence_first", "any_block", "heuristic"]


def _is_valid_python(code: str) -> bool:
    """Return True if the string parses as valid Python."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _contains_function(code: str) -> bool:
    """Return True if the code defines at least one function."""
    return bool(re.search(r"^\s*def\s+\w+", code, re.MULTILINE))


def _extract_fence_first(text: str) -> str | None:
    """
    Extract code from the first (or longest) python-labelled fence block.
    """
    candidates: list[str] = []
    for m in _FENCE_RE.finditer(text):
        lang = (m.group("lang") or "").lower().strip()
        code = m.group("code").strip()
        if not code:
            continue
        if lang in ("python", "py", ""):
            candidates.append(code)

    if not candidates:
        return None
    # Prefer the longest candidate (likely the full solution)
    return max(candidates, key=len)


def _extract_any_block(text: str) -> str | None:
    """
    Extract from any fence block whose content parses as Python.
    """
    best: str | None = None
    for m in _FENCE_RE.finditer(text):
        code = m.group("code").strip()
        if not code:
            continue
        if _is_valid_python(code):
            if best is None or len(code) > len(best):
                best = code
    return best


def _extract_heuristic(text: str) -> str | None:
    """
    Fallback: look for 'def ' and extract from there.
    """
    lines = text.splitlines()
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*def\s+\w+", line):
            start_idx = i
            break

    if start_idx is None:
        return None

    # Take all lines from the first def to the end, then trim trailing prose
    code_lines = lines[start_idx:]
    # Remove trailing lines that are clearly prose (no indentation, no python)
    while code_lines and not code_lines[-1].startswith((" ", "\t")) and \
            not re.match(r"^\s*(def|class|return|if|for|while|import|from|#)", code_lines[-1]):
        code_lines.pop()

    return "\n".join(code_lines).strip() or None


def extract_code(
    text: str,
    strategy: ExtractionStrategy = "fence_first",
    entry_point: str | None = None,
) -> str:
    """
    Extract Python code from a model response string.

    Parameters
    ----------
    text:
        Full raw model output.
    strategy:
        Extraction strategy: 'fence_first', 'any_block', or 'heuristic'.
    entry_point:
        If provided and a fence block doesn't contain this function name,
        we keep searching (helps when the model defines a wrapper then the
        actual function separately).

    Returns
    -------
    Extracted code string, or empty string if nothing found.
    """
    if not text or not text.strip():
        return ""

    code: str | None = None

    if strategy in ("fence_first", "any_block"):
        code = _extract_fence_first(text)

        # If fence_first found nothing, or the block lacks the entry_point function,
        # try any_block
        if (code is None or (entry_point and entry_point not in code)) and \
                strategy == "any_block":
            code = _extract_any_block(text)

        # Fall through to heuristic if still nothing
        if code is None:
            code = _extract_heuristic(text)

    elif strategy == "heuristic":
        code = _extract_heuristic(text)
    else:
        code = _extract_fence_first(text) or _extract_heuristic(text)

    if code is None:
        logger.debug("Code extraction failed (strategy=%s); returning empty string.", strategy)
        return ""

    code = code.strip()

    # Sanity check
    if not _is_valid_python(code):
        logger.warning(
            "Extracted code does not parse as valid Python "
            "(entry_point=%s, first 80 chars: %r). Returning as-is.",
            entry_point, code[:80],
        )

    return code
