"""
chaintrust/runner/peer_review.py
Peer-review task execution for ChainTrust Phase 4.
Agents evaluate peer code solutions blindly (ratee identity hidden).
Extracts rating ∈ [0.0, 1.0] and justification, persisting records to peer_ratings table.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from chaintrust.db.models import Agent, Interaction, PeerRating, Task
from chaintrust.db.session import get_session
from chaintrust.runner.clients import GenerateResult, get_client
from chaintrust.runner.rate_limiter import RateLimiter, build_limiters

logger = logging.getLogger(__name__)

PEER_REVIEW_PROMPT_TEMPLATE = """You are an expert software engineer reviewing a Python solution for a coding problem.

Problem:
{task_prompt}

Candidate Solution:
```python
{candidate_code}
```

Sandbox test outcome: {test_status}.

Please evaluate the code quality, logical correctness, efficiency, and robustness.
At the end of your response, strictly output your numerical score and justification in the following format:
RATING: <float between 0.0 and 1.0>
JUSTIFICATION: <one or two sentence summary>
"""


def format_peer_review_prompt(task_prompt: str, candidate_code: str, test_status: str = "Passed") -> str:
    """Format review prompt with ratee identity strictly hidden from reviewer."""
    return PEER_REVIEW_PROMPT_TEMPLATE.format(
        task_prompt=task_prompt.strip(),
        candidate_code=candidate_code.strip(),
        test_status=test_status.strip(),
    )


def parse_peer_review_response(response_text: str) -> Tuple[float, str]:
    """
    Parses RATING and JUSTIFICATION from model output.
    Returns:
        (rating in [0.0, 1.0], justification string)
    """
    if not response_text:
        return 0.5, "No response provided"

    # Search for RATING: <float>
    rating_match = re.search(r"RATING:\s*([0-1](?:\.\d+)?|\d+(?:\.\d+)?)", response_text, re.IGNORECASE)
    if rating_match:
        try:
            val = float(rating_match.group(1))
            val = max(0.0, min(1.0, val))
        except ValueError:
            val = 0.5
    else:
        # Fallback search for any score/rating pattern
        num_match = re.search(r"(?:score|rating)[^\d]*([0-1](?:\.\d+)?|\b[0-9]\b(?:\.\d+)?)", response_text, re.IGNORECASE)
        if num_match:
            try:
                raw_val = float(num_match.group(1))
                val = max(0.0, min(1.0, raw_val if raw_val <= 1.0 else raw_val / 10.0))
            except ValueError:
                val = 0.5
        else:
            val = 0.5

    # Search for JUSTIFICATION: <text>
    just_match = re.search(r"JUSTIFICATION:\s*(.+)", response_text, re.IGNORECASE | re.DOTALL)
    if just_match:
        justification = just_match.group(1).strip()
    else:
        lines = [line.strip() for line in response_text.splitlines() if line.strip()]
        justification = lines[-1] if lines else "Automated peer review"

    return round(val, 6), justification


def execute_peer_review(
    rater_agent: Agent,
    ratee_agent: Agent,
    task: Task,
    candidate_code: str,
    test_status: str = "Passed",
    client: Optional[Any] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> PeerRating:
    """
    Executes a single peer review where rater_agent reviews ratee_agent's solution.
    Saves and returns the PeerRating object.
    """
    prompt = format_peer_review_prompt(
        task_prompt=task.prompt,
        candidate_code=candidate_code,
        test_status=test_status,
    )

    if rate_limiter:
        rate_limiter.acquire()

    if client is None:
        client = get_client(rater_agent.provider)

    gen_res: GenerateResult = client.generate(
        model=rater_agent.model,
        prompt=prompt,
        system_prompt="You are an objective, rigorous, and fair code reviewer.",
    )

    raw_output = gen_res.text or ""
    raw_hash = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()

    rating_val, justification = parse_peer_review_response(raw_output)

    peer_rating = PeerRating(
        rater_id=rater_agent.agent_id,
        ratee_id=ratee_agent.agent_id,
        task_id=task.task_id,
        rating=rating_val,
        justification=justification[:1000],
        raw_output_hash=raw_hash,
        timestamp=datetime.now(timezone.utc),
    )

    # Persist to disk cache
    out_dir = Path("data/outputs/peer_reviews")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"review_{rater_agent.agent_id[:8]}_{ratee_agent.agent_id[:8]}_{task.task_id.replace('/', '_')}.txt"
    out_file.write_text(raw_output, encoding="utf-8")

    return peer_rating
