"""Safety rule: transient API errors are retried; anything else fails fast."""

import httpx
import openai
import pytest
from langchain_core.runnables import RunnableLambda

from portalguard.llm import with_api_retries


def flaky(failures: int, error):
    calls = []

    def call(_):
        calls.append(1)
        if len(calls) <= failures:
            raise error
        return "ok"

    return RunnableLambda(call), calls


def connection_error():
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def test_transient_errors_are_retried():
    runnable, calls = flaky(2, connection_error())
    assert with_api_retries(runnable, attempts=3, backoff=False).invoke("x") == "ok"
    assert len(calls) == 3


def test_gives_up_after_the_last_attempt():
    runnable, calls = flaky(5, connection_error())
    with pytest.raises(openai.APIConnectionError):
        with_api_retries(runnable, attempts=3, backoff=False).invoke("x")
    assert len(calls) == 3


def test_non_transient_errors_are_not_retried():
    runnable, calls = flaky(1, ValueError("bad request"))
    with pytest.raises(ValueError):
        with_api_retries(runnable, attempts=3, backoff=False).invoke("x")
    assert len(calls) == 1
