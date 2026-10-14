"""LangSmith tracing: on for every run when LANGSMITH_API_KEY is set (keys come only from .env).

LangChain and LangGraph trace themselves once LANGSMITH_TRACING=true: every node, LLM call and tool
call becomes a span. Harness work outside LangChain (triage's own pytest runs) uses @traceable.
"""

import os

from dotenv import load_dotenv

from portalguard.config import REPO_ROOT

DEFAULT_PROJECT = "portalguard"


def setup_tracing() -> str:
    """Load .env and turn tracing on if a LangSmith key exists. Returns a status line (never the key)."""
    load_dotenv(REPO_ROOT / ".env")
    if not os.environ.get("LANGSMITH_API_KEY"):
        os.environ["LANGSMITH_TRACING"] = "false"
        return "LangSmith tracing off (no LANGSMITH_API_KEY)"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_PROJECT", DEFAULT_PROJECT)
    return f"LangSmith tracing on (project: {os.environ['LANGSMITH_PROJECT']})"


def run_config(run_id: str, release_url: str, mock: bool) -> dict:
    """Name, tags and metadata so runs are easy to find and filter in LangSmith."""
    return {"run_name": f"portalguard-qe {run_id}",
            "tags": ["portalguard", "mock" if mock else "real", release_url.rstrip("/").rsplit("/", 1)[-1]],
            "metadata": {"run_id": run_id, "release_url": release_url, "mode": "mock" if mock else "real"}}


def project() -> str:
    return os.environ.get("LANGSMITH_PROJECT", DEFAULT_PROJECT)


def in_project():
    """Trace the enclosed work as a new root run in the main project.

    langsmith.evaluate() nests everything the target does under the experiment's own project. This
    keeps every QE run in the same LangSmith project, whether it came from the CLI or an eval.
    """
    from langsmith import tracing_context
    return tracing_context(project_name=project(), parent=False)


def flush() -> None:
    """Send pending traces before the process exits."""
    from langchain_core.tracers.langchain import wait_for_all_tracers
    wait_for_all_tracers()
