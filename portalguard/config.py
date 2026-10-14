"""Settings in one place: paths, budgets, allowlist, prices, journeys."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTAL_DIR = REPO_ROOT / "portal"
TEST_USERS_FILE = PORTAL_DIR / "test-users.json"
RUNS_DIR = REPO_ROOT / "runs"
CHECKPOINT_DB = RUNS_DIR / "checkpoints.sqlite"

PORT = 8000
GOOD_URL = f"http://localhost:{PORT}/good/"
BUGGY_URL = f"http://localhost:{PORT}/buggy/"

MODEL = "gpt-4.1-mini"
# USD per 1M tokens (input, output). Check current OpenAI pricing before relying on these.
PRICES_PER_1M = {"gpt-4.1-mini": (0.40, 1.60), "mock": (0.0, 0.0)}

# Budgets, checked before every LLM call (all agents in a run share one budget).
MAX_STEPS = 40            # LLM calls per run (planner + every sub-agent turn)
MAX_TOKENS = 300_000      # prompt + completion, summed
MAX_COST_USD = 0.25
MAX_SUBAGENT_STEPS = 5    # LLM calls per journey sub-agent per task
MAX_HEAL_ATTEMPTS = 3     # write_test retries per file after a broken_test verdict
MAX_DIFF_CHECKS = 2       # extra diff-check to-dos the planner may add
MAX_PARALLEL = 4          # journey sub-agents running at once (each launches a browser)
LLM_RETRIES = 3           # attempts for transient API errors (connection, timeout, rate limit, 5xx)

ALLOWED_HOSTS = {"localhost", "127.0.0.1"}

# Journey key -> display name. diff_check = a test for a snapshot diff (no journey of its own).
JOURNEYS = {
    "sign_in": "Sign in",
    "wrong_password": "Wrong password shows an error",
    "appointments": "See upcoming appointments",
    "lab_results": "View lab results",
    "download_pdf": "Download lab results PDF",
    "diff_check": None,
}
REQUIRED_JOURNEYS = [key for key, name in JOURNEYS.items() if name]
