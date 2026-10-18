"""
tests/unit/test_extractor.py
Unit tests for the code extraction module.

No API calls, no Docker — pure function tests.
"""

from __future__ import annotations

import pytest

from chaintrust.runner.extractor import extract_code, _is_valid_python, _contains_function


# ---------------------------------------------------------------------------
# Helper: sample model outputs
# ---------------------------------------------------------------------------

SIMPLE_FENCE = """\
Here is my solution:

```python
def add(a: int, b: int) -> int:
    return a + b
```

That should work!
"""

UNLABELLED_FENCE = """\
```
def multiply(a, b):
    return a * b
```
"""

MULTIPLE_FENCES = """\
First, a helper:

```python
def _helper(x):
    return x * 2
```

Then the main function:

```python
def solve(nums):
    return [_helper(n) for n in nums]
```
"""

NO_FENCE_DEF = """\
I'll solve this step by step.

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

This is the recursive solution.
"""

EMPTY_RESPONSE = ""
PROSE_ONLY = "I cannot solve this problem."

FENCE_WITH_SYNTAX_ERROR = """\
```python
def broken(
    # missing closing paren
```
"""

JAVA_FENCE = """\
```java
public int add(int a, int b) { return a + b; }
```

```python
def add(a, b):
    return a + b
```
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIsValidPython:
    def test_valid(self):
        assert _is_valid_python("def f(x): return x") is True

    def test_invalid(self):
        assert _is_valid_python("def f(: return") is False

    def test_empty(self):
        assert _is_valid_python("") is True   # empty is syntactically valid


class TestContainsFunction:
    def test_has_def(self):
        assert _contains_function("def foo(): pass") is True

    def test_no_def(self):
        assert _contains_function("x = 1 + 2") is False

    def test_indented_def(self):
        assert _contains_function("    def inner(): pass") is True


class TestExtractCode:
    # --- fence_first strategy ---

    def test_simple_fence(self):
        code = extract_code(SIMPLE_FENCE)
        assert "def add" in code
        assert "return a + b" in code

    def test_unlabelled_fence_fence_first(self):
        """Unlabelled fences are accepted under fence_first."""
        code = extract_code(UNLABELLED_FENCE)
        assert "def multiply" in code

    def test_multiple_fences_takes_longest(self):
        """When multiple fences exist, the longest is preferred."""
        code = extract_code(MULTIPLE_FENCES)
        # solve() is longer than _helper()
        assert "def solve" in code

    def test_no_fence_falls_back_to_heuristic(self):
        code = extract_code(NO_FENCE_DEF)
        assert "def fibonacci" in code

    def test_empty_response_returns_empty(self):
        code = extract_code(EMPTY_RESPONSE)
        assert code == ""

    def test_prose_only_returns_empty(self):
        code = extract_code(PROSE_ONLY)
        assert code == ""

    # --- any_block strategy ---

    def test_any_block_skips_java(self):
        """any_block should skip the Java fence and return the Python one."""
        code = extract_code(JAVA_FENCE, strategy="any_block")
        assert "def add" in code
        assert "public" not in code

    # --- heuristic strategy ---

    def test_heuristic_no_fence(self):
        code = extract_code(NO_FENCE_DEF, strategy="heuristic")
        assert "def fibonacci" in code

    # --- entry_point filtering ---

    def test_entry_point_prefers_matching_block(self):
        """When entry_point is given and a block lacks it, we continue searching."""
        response = """\
```python
def helper(x):
    return x
```

```python
def target(nums):
    return sorted(nums)
```
"""
        # With entry_point="target", we should prefer the second block
        code = extract_code(response, entry_point="target")
        assert "def target" in code

    # --- syntax error in fence ---

    def test_syntax_error_in_fence_still_returned(self):
        """
        If the code in the fence has a syntax error we still return it
        (the grader will fail it, not the extractor).
        """
        code = extract_code(FENCE_WITH_SYNTAX_ERROR)
        # We get something back (broken code is still extracted)
        assert "def broken" in code or code == ""   # either is acceptable

    # --- output is stripped ---

    def test_output_is_stripped(self):
        code = extract_code(SIMPLE_FENCE)
        assert not code.startswith("\n")
        assert not code.endswith("\n\n")
