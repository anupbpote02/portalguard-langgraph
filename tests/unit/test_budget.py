"""Safety rule: step, token and cost budgets are checked before every LLM call."""

import pytest

from portalguard.agents import RunContext
from portalguard.llm import ScriptedChatModel
from portalguard.safety import Budget, BudgetExceeded
from langchain_core.messages import AIMessage


def test_step_budget_stops_the_next_call():
    budget = Budget(max_steps=2)
    budget.check()
    budget.check()
    with pytest.raises(BudgetExceeded, match="max_steps"):
        budget.check()


def test_token_and_cost_budgets():
    tokens = Budget(max_tokens=100)
    tokens.add(100, 0.0)
    with pytest.raises(BudgetExceeded, match="max_tokens"):
        tokens.check()
    cost = Budget(max_cost_usd=0.01)
    cost.add(10, 0.02)
    with pytest.raises(BudgetExceeded, match="max_cost"):
        cost.check()


def test_budget_resumes_from_checkpointed_usage():
    budget = Budget(max_steps=5, used={"steps": 5, "tokens": 0, "cost_usd": 0})
    with pytest.raises(BudgetExceeded):
        budget.check()


def test_model_is_not_called_once_budget_is_spent():
    calls = []
    model = ScriptedChatModel(script=lambda messages: calls.append(1) or AIMessage(content="hi"))
    ctx = RunContext(model=model, budget=Budget(max_steps=1))
    ctx.call_model(model, ["hello"])
    with pytest.raises(BudgetExceeded):
        ctx.call_model(model, ["hello again"])
    assert len(calls) == 1
    assert ctx.budget.snapshot()["tokens"] > 0  # mock usage is counted too
