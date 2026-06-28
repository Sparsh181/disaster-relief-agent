"""
Rate Limiter
-------------
Simple in-memory rate limiter for MCP server tools.
Prevents abuse of external APIs (GDACS, Open-Meteo, Gemini)
and protects against runaway agent loops.

Uses a sliding window approach — tracks call timestamps
per tool and rejects calls that exceed the limit.

Limits:
  - get_disaster_alerts : 10 calls/minute (GDACS fair use)
  - get_weather         : 20 calls/minute (Open-Meteo fair use)
  - get_full_briefing   : 5 calls/minute  (LLM quota protection)
  - default             : 10 calls/minute
"""

import time
from collections import defaultdict, deque
from datetime import datetime


# ── Per-tool rate limits (calls per minute) ─────────────────
RATE_LIMITS = {
    "get_disaster_alerts": 10,
    "get_weather"        : 20,
    "get_full_briefing"  : 5,
}
DEFAULT_LIMIT = 10
WINDOW_SECONDS = 60  # sliding window size


class RateLimiter:
    """
    Sliding window rate limiter.
    Tracks call timestamps per tool name and rejects
    calls that exceed the configured limit.
    """

    def __init__(self):
        # tool_name → deque of call timestamps
        self._calls = defaultdict(deque)
        # tool_name → total calls made (for metrics)
        self._total_calls    = defaultdict(int)
        self._rejected_calls = defaultdict(int)

    def check(self, tool_name: str) -> tuple[bool, str]:
        """
        Check if a tool call is allowed under the rate limit.

        Args:
            tool_name: Name of the tool being called

        Returns:
            (allowed: bool, message: str)
            If allowed: (True, "")
            If rejected: (False, rejection reason message)
        """
        now   = time.time()
        limit = RATE_LIMITS.get(tool_name, DEFAULT_LIMIT)
        calls = self._calls[tool_name]

        # Remove timestamps outside the sliding window
        while calls and now - calls[0] > WINDOW_SECONDS:
            calls.popleft()

        # Check if limit exceeded
        if len(calls) >= limit:
            self._rejected_calls[tool_name] += 1
            oldest  = calls[0]
            wait    = int(WINDOW_SECONDS - (now - oldest)) + 1
            message = (
                f"Rate limit exceeded for '{tool_name}': "
                f"{limit} calls per {WINDOW_SECONDS}s allowed. "
                f"Please retry in {wait} seconds."
            )
            return False, message

        # Allow — record this call
        calls.append(now)
        self._total_calls[tool_name] += 1
        return True, ""

    def get_stats(self) -> dict:
        """
        Returns rate limiter statistics for eval metrics.
        """
        now   = time.time()
        stats = {}

        all_tools = set(
            list(self._total_calls.keys()) +
            list(self._rejected_calls.keys())
        )

        for tool in all_tools:
            calls = self._calls[tool]
            # Count calls in current window
            recent = sum(1 for t in calls if now - t <= WINDOW_SECONDS)
            limit  = RATE_LIMITS.get(tool, DEFAULT_LIMIT)

            stats[tool] = {
                "total_calls"   : self._total_calls[tool],
                "rejected_calls": self._rejected_calls[tool],
                "calls_in_window": recent,
                "limit_per_min" : limit,
                "utilization"   : f"{recent}/{limit}"
            }

        return stats

    def reset(self, tool_name: str = None):
        """
        Reset rate limit counters.
        Pass tool_name to reset one tool, or None to reset all.
        """
        if tool_name:
            self._calls[tool_name].clear()
            self._total_calls[tool_name]    = 0
            self._rejected_calls[tool_name] = 0
        else:
            self._calls.clear()
            self._total_calls.clear()
            self._rejected_calls.clear()


# ── Global rate limiter instance ────────────────────────────
# Shared across all tool calls in the same process
rate_limiter = RateLimiter()


def rate_limited(tool_name: str):
    """
    Decorator factory for rate-limiting tool functions.

    Usage:
        @rate_limited("get_disaster_alerts")
        def get_disaster_alerts(...):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            allowed, message = rate_limiter.check(tool_name)
            if not allowed:
                import json
                print(f"[RateLimiter] REJECTED: {message}")
                return json.dumps({
                    "error"      : message,
                    "rate_limited": True,
                    "tool"       : tool_name
                })
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__  = func.__doc__
        return wrapper
    return decorator