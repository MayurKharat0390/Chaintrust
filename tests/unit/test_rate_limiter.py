"""
tests/unit/test_rate_limiter.py
Unit tests for the RateLimiter.

All tests use real time but very small windows (mocked via monkeypatching
time.monotonic where needed) to avoid slow tests.
"""

from __future__ import annotations

import threading
import time

import pytest

from chaintrust.runner.rate_limiter import RateLimiter, build_limiters


class TestRateLimiter:
    def test_allows_up_to_rpm(self):
        """Should allow exactly rpm requests without blocking."""
        limiter = RateLimiter("test", rpm=5, rpd=1000)
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - start
        # Should complete almost instantly (< 0.5s)
        assert elapsed < 0.5

    def test_stats_after_acquire(self):
        limiter = RateLimiter("test", rpm=10, rpd=100)
        limiter.acquire()
        stats = limiter.stats()
        assert stats["used_per_minute"] == 1
        assert stats["used_per_day"] == 1

    def test_thread_safe(self):
        """Multiple threads should not exceed the RPM limit."""
        limiter = RateLimiter("test", rpm=10, rpd=1000)
        acquired = []

        def worker():
            limiter.acquire()
            acquired.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All 10 should complete (rpm=10 allows all)
        assert len(acquired) == 10

    def test_rpd_tracked_separately(self):
        limiter = RateLimiter("test", rpm=100, rpd=3)
        for _ in range(3):
            limiter.acquire()
        stats = limiter.stats()
        assert stats["used_per_day"] == 3

    def test_stats_keys(self):
        limiter = RateLimiter("myprovider", rpm=10, rpd=100)
        stats = limiter.stats()
        assert "provider" in stats
        assert stats["provider"] == "myprovider"
        assert "used_per_minute" in stats
        assert "limit_per_minute" in stats
        assert "used_per_day" in stats
        assert "limit_per_day" in stats


class TestBuildLimiters:
    AGENTS = [
        {"provider": "groq", "rate_limits": {"requests_per_minute": 30, "requests_per_day": 14400}},
        {"provider": "groq", "rate_limits": {"requests_per_minute": 20, "requests_per_day": 10000}},
        {"provider": "gemini"},   # no rate_limits → uses global
    ]
    GLOBAL = {"requests_per_minute": 10, "requests_per_day": 1000}

    def test_returns_one_limiter_per_provider(self):
        limiters = build_limiters(self.AGENTS, self.GLOBAL)
        assert "groq" in limiters
        assert "gemini" in limiters
        assert len(limiters) == 2

    def test_takes_minimum_for_same_provider(self):
        """Two groq agents → use the strictest (min) limits."""
        limiters = build_limiters(self.AGENTS, self.GLOBAL)
        groq_limiter = limiters["groq"]
        assert groq_limiter.rpm == 20    # min(30, 20)
        assert groq_limiter.rpd == 10000 # min(14400, 10000)

    def test_global_limits_applied_when_no_override(self):
        """Gemini agent has no rate_limits → uses global."""
        limiters = build_limiters(self.AGENTS, self.GLOBAL)
        assert limiters["gemini"].rpm == 10
        assert limiters["gemini"].rpd == 1000
