"""Chat models: ChatOpenAI (gpt-4.1-mini, temperature 0) or a scripted fake model for --mock ($0, no key).

Both are LangChain BaseChatModels, so the graph code is identical in both modes, and LangSmith
traces both the same way.
"""

import json
import os
from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable

from portalguard.config import LLM_RETRIES, MODEL, PRICES_PER_1M


class ScriptedChatModel(BaseChatModel):
    """Fake chat model: `script(messages) -> AIMessage` decides each reply.

    The script is a pure function of the conversation (no shared iterator), so parallel sub-agents
    can use one instance safely. Token counts are estimated (~4 chars/token) so budgets still apply.
    """

    script: Callable[[list[BaseMessage]], AIMessage]
    model_name: str = "mock"

    @property
    def _llm_type(self) -> str:
        return "portalguard-scripted-mock"

    def bind_tools(self, tools, **kwargs) -> Runnable:
        return self  # the script already knows which tools exist

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        reply = self.script(messages)
        prompt_chars = sum(len(str(m.content)) for m in messages)
        completion_chars = len(str(reply.content)) + len(json.dumps([c["args"] for c in reply.tool_calls]))
        reply.usage_metadata = {"input_tokens": prompt_chars // 4, "output_tokens": completion_chars // 4,
                                "total_tokens": (prompt_chars + completion_chars) // 4}
        return ChatResult(generations=[ChatGeneration(message=reply)])


def make_model(mock: bool, script: Callable | None = None) -> BaseChatModel:
    if mock:
        from portalguard.mock import respond
        return ScriptedChatModel(script=script or respond)
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Put it in .env (see .env.example) or use --mock.")
    from langchain_openai import ChatOpenAI
    # max_retries=0: retries happen in with_api_retries, so they are visible and tested.
    return ChatOpenAI(model=MODEL, temperature=0, max_tokens=4000, max_retries=0, timeout=60)


def retryable_errors() -> tuple[type[Exception], ...]:
    """Transient API problems worth retrying: connection, timeout, rate limit, 5xx."""
    import openai
    return (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError)


def with_api_retries(runnable: Runnable, attempts: int = LLM_RETRIES, backoff: bool = True) -> Runnable:
    """LangChain's Runnable.with_retry with exponential backoff, only for transient errors."""
    return runnable.with_retry(retry_if_exception_type=retryable_errors(), stop_after_attempt=attempts,
                               wait_exponential_jitter=backoff)


def model_name(model: BaseChatModel) -> str:
    return getattr(model, "model_name", None) or MODEL


def usage_cost(message: AIMessage, model: str) -> tuple[int, float]:
    """(total tokens, USD) for one reply, from LangChain's usage_metadata."""
    usage = message.usage_metadata or {}
    tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    price_in, price_out = PRICES_PER_1M.get(model, PRICES_PER_1M[MODEL])
    return tokens_in + tokens_out, (tokens_in * price_in + tokens_out * price_out) / 1_000_000
