"""
chaintrust/runner/rate_limiter.py
Per-provider token-bucket rate limiter with per-minute and per-day limits.

Design
------
* One RateLimiter instance per provider.
* Two sliding windows: per-minute and per-day.
* `acquire()` blocks (sleeps) until a request slot is available.
* Thread-safe via a threading.Lock.

The Runner creates one RateLimiter per provider from the config and passes
it to the worker threads.  Workers call `limiter.acquire()` before every
API request.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding-window rate limiter enforcing two simultaneous limits:
    - requests_per_minute (RPM)
    - requests_per_day    (RPD)

    Usage
    -----
        limiter = RateLimiter("groq", rpm=30, rpd=14400)
        limiter.acquire()   # blocks until a slot is free
        # ... make API call ...
    """

    def __init__(self, provider: str, rpm: int, rpd: int) -> None:
        self.provider = provider
        self.rpm = rpm
        self.rpd = rpd
        self._lock = threading.Lock()
        # Timestamps of recent requests (monotonic seconds)
        self._minute_window: deque[float] = deque()
        self._day_window:    deque[float] = deque()

    def acquire(self) -> None:
        """
        Block until this provider has capacity for one more request.

        Sleeps in 0.1s increments and logs when it's waiting.
        """
        while True:
            with self._lock:
                now = time.monotonic()
                self._prune(now)

                rpm_ok = len(self._minute_window) < self.rpm
                rpd_ok = len(self._day_window)    < self.rpd

                if rpm_ok and rpd_ok:
                    self._minute_window.append(now)
                    self._day_window.append(now)
                    return

                # Compute next available slot time
                if not rpm_ok:
                    oldest_min = self._minute_window[0]
                    wait = max(0.0, oldest_min + 60.0 - now)
                    reason = "RPM"
                else:
                    oldest_day = self._day_window[0]
                    wait = max(0.0, oldest_day + 86400.0 - now)
                    reason = "RPD"

            logger.info(
                "[%s] Rate limit (%s): waiting %.1fs …",
                self.provider, reason, wait,
            )
            time.sleep(min(wait, 5.0))  # sleep in chunks so we can re-check

    def _prune(self, now: float) -> None:
        """Remove timestamps older than the relevant windows."""
        cutoff_min = now - 60.0
        cutoff_day = now - 86400.0
        while self._minute_window and self._minute_window[0] < cutoff_min:
            self._minute_window.popleft()
        while self._day_window and self._day_window[0] < cutoff_day:
            self._day_window.popleft()

    def stats(self) -> dict[str, int]:
        """Return current usage counts (for logging/debugging)."""
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            return {
                "provider":         self.provider,
                "used_per_minute":  len(self._minute_window),
                "limit_per_minute": self.rpm,
                "used_per_day":     len(self._day_window),
                "limit_per_day":    self.rpd,
            }


def build_limiters(agents_configs: list[dict], global_limits: dict) -> dict[str, RateLimiter]:
    """
    Build one RateLimiter per provider from agent configs and global defaults.

    Per-agent rate_limits override the global defaults for that provider.
    The strictest limits across all agents of the same provider are used
    (i.e., we respect the lowest RPM/RPD seen for that provider).

    Parameters
    ----------
    agents_configs:
        List of raw agent config dicts from agents.yaml.
    global_limits:
        Dict with keys 'requests_per_minute' and 'requests_per_day'.

    Returns
    -------
    Dict mapping provider name → RateLimiter.
    """
    # Accumulate limits per provider: take the MINIMUM (most restrictive)
    provider_limits: dict[str, dict[str, int]] = {}

    for agent in agents_configs:
        provider = agent.get("provider", "unknown")
        agent_lim = agent.get("rate_limits", {})
        rpm = agent_lim.get("requests_per_minute", global_limits.get("requests_per_minute", 10))
        rpd = agent_lim.get("requests_per_day",    global_limits.get("requests_per_day",    1000))

        if provider not in provider_limits:
            provider_limits[provider] = {"rpm": rpm, "rpd": rpd}
        else:
            # Take minimum (most conservative)
            provider_limits[provider]["rpm"] = min(provider_limits[provider]["rpm"], rpm)
            provider_limits[provider]["rpd"] = min(provider_limits[provider]["rpd"], rpd)

    limiters: dict[str, RateLimiter] = {}
    for provider, limits in provider_limits.items():
        limiters[provider] = RateLimiter(
            provider=provider,
            rpm=limits["rpm"],
            rpd=limits["rpd"],
        )
        logger.info(
            "Rate limiter created: provider=%s rpm=%d rpd=%d",
            provider, limits["rpm"], limits["rpd"],
        )

    return limiters
