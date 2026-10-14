"""Safety rules the graph nodes enforce. Plain code, unit tested, no LLM involved."""

import threading
from urllib.parse import urlparse

from portalguard.config import ALLOWED_HOSTS, MAX_COST_USD, MAX_STEPS, MAX_TOKENS


class BudgetExceeded(Exception):
    """Raised before an LLM call that would go over a budget. The graph stops cleanly."""


def check_url(url: str) -> None:
    """Healthcare rule: the agent may only open localhost. Raises ValueError otherwise."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"URL not allowed (localhost only): {url}")


class Budget:
    """Steps, tokens and cost shared by every agent in one run (parallel sub-agents too, hence the lock).

    check() runs BEFORE each LLM call, so one call can overshoot by at most its own size.
    """

    def __init__(self, max_steps=MAX_STEPS, max_tokens=MAX_TOKENS, max_cost_usd=MAX_COST_USD,
                 used: dict | None = None):
        self.max_steps, self.max_tokens, self.max_cost_usd = max_steps, max_tokens, max_cost_usd
        used = used or {}
        self.steps = used.get("steps", 0)
        self.tokens = used.get("tokens", 0)
        self.cost_usd = used.get("cost_usd", 0.0)
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.steps >= self.max_steps:
                raise BudgetExceeded(f"max_steps ({self.max_steps}) reached")
            if self.tokens >= self.max_tokens:
                raise BudgetExceeded(f"max_tokens ({self.max_tokens}) reached")
            if self.cost_usd >= self.max_cost_usd:
                raise BudgetExceeded(f"max_cost_usd (${self.max_cost_usd}) reached")
            self.steps += 1  # reserve the step now, so parallel agents can't all pass the check at once

    def add(self, tokens: int, cost_usd: float) -> None:
        with self._lock:
            self.tokens += tokens
            self.cost_usd += cost_usd

    def snapshot(self) -> dict:
        with self._lock:
            return {"steps": self.steps, "tokens": self.tokens, "cost_usd": round(self.cost_usd, 6)}
