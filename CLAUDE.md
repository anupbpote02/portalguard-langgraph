# PortalGuard (LangChain + LangGraph edition)

An AI QE agent that tests each release of a (fictional) hospital patient portal. It diffs
accessibility (aria) snapshots of the main page **and every iframe** against the last good release,
plans journey tests, writes and runs Playwright tests with one sub-agent per journey, triages
failures against the baseline, heals broken tests, asks a human to approve, and writes a report.

Rebuild of `../portalguard` (custom harness) on the stack the interviewer (Bitcot) suggested:
**LangChain, LangGraph, LangSmith, deep-agent pattern**. Keep it simple and working over clever.

## Working style

- Build in phases (below). After each phase: run it, verify, commit (clear message, no
  Co-Authored-By trailer), 3-line summary, continue.
- `--mock` (fake chat model, $0, no key) is the default for tests and CI.
- Keys only from `.env` (gitignored). Never print them.
- Windows + OneDrive folder: paths via pathlib, `sys.executable`, no shell-specific tricks.
- Synthetic data only (Jordan Rivera, MRN TEST-000123 and two other test users).

## Stack

Python 3.12, langchain-core + langchain-openai (`ChatOpenAI`, gpt-4.1-mini, temperature 0),
langgraph (`StateGraph`, `Send`, `interrupt`, SQLite checkpointer), langsmith (tracing,
datasets, experiments), Playwright (sync) + pytest + pytest-playwright, python-dotenv.

## Layout

```
portal/good, portal/buggy, portal/test-users.json   copied from ../portalguard (4 planted bugs)
portalguard/
  config.py     budgets, allowlist, prices, journeys, paths
  llm.py        make_model(): ChatOpenAI or ScriptedChatModel (mock); API retries; usage -> cost
  browser.py    Playwright + pytest helpers (aria snapshots, diff, AST checks, JUnit parsing)
  tools.py      LangChain @tool: snapshot_page, compare_snapshots, write_test, run_tests
  safety.py     Budget, check_url, validate tool args
  coverage.py   per-journey static rules (ported)
  triage.py     baseline-as-oracle verdicts + real-bug lock (ported, state is plain dicts)
  agents.py     planner (to-do list) + journey sub-agent loop
  graph.py      StateGraph: snapshot -> compare -> planner -> journeys (Send) -> triage -> heal|approve -> report
  report.py     report.md from graph state, never from model text
  mock.py       scripted responses for the fake chat model
  fixtures.py   pytest plugin for generated tests (patient, signed_in, localhost-only route guard)
  main.py       CLI: python -m portalguard.main --mock|--real [--release buggy] [--auto-approve]
evals/expected_bugs.json, evals/scoring.py, evals/run_eval.py (LangSmith dataset + experiment)
tests/unit/     one short test per safety rule + scoring
runs/<id>/      snapshots/, tests/, test-results/, report.md   (gitignored); runs/checkpoints.sqlite
```

## Graph

1. `snapshot`: snapshot_page baseline (good) + release. Full aria data to disk, summary in state.
2. `compare`: compare_snapshots -> diff lines per page / frame.
3. `planner`: LLM writes the to-do list (`write_todos`): sign_in, wrong_password, appointments,
   lab_results, download_pdf + diff checks. Harness adds any missing required journey.
4. `journey` sub-agents, one per to-do, in parallel via `Send` (isolated context each):
   write_test -> run_tests on the release.
5. `triage` (deterministic) then a conditional edge: broken tests with heal attempts left ->
   `Send` heal tasks back to `journey`; otherwise -> `approve`.
6. `approve`: `interrupt()` for human approval (skipped with `--auto-approve`).
7. `report`: runs/<id>/report.md.

"The model proposes, the harness decides": pass/fail comes from Playwright, verdicts from triage.

## Safety rules (inside nodes, each with a unit test)

- Budgets: MAX_STEPS (LLM calls), MAX_TOKENS, MAX_COST_USD, checked before every LLM call.
- Allowlist: only localhost / 127.0.0.1 URLs (tools, CLI, and a browser route guard in fixtures).
- Argument validation: pydantic tool schemas (journey is a Literal enum), filename pattern, AST
  checks on test code (allowed imports, no exec/eval/open/dunders).
- Baseline-as-oracle lock: failing test runs on baseline first (fails there = broken test);
  a test proving a real bug can't be rewritten.
- Coverage check: a journey test must exercise its journey; the plan must contain all journeys.
- API retries: transient OpenAI errors retried with backoff (`Runnable.with_retry`).

## Portal

`python -m http.server 8000 --directory portal` (main.py / evals start it if needed).
Good: http://localhost:8000/good/, buggy: http://localhost:8000/buggy/.

| ID    | Bug                                               | Type          | File             |
|-------|---------------------------------------------------|---------------|------------------|
| BUG-1 | "Sign in" button has no accessible name           | accessibility | index.html       |
| BUG-2 | "Upcoming appointments" heading removed           | accessibility | dashboard.html   |
| BUG-3 | "Lab results" heading removed (in iframe)         | accessibility | lab-results.html |
| BUG-4 | "Download PDF" does nothing                       | functional    | lab-results.html |

## Phases

1. Setup: branch main, requirements, .env.example, .gitignore, CLAUDE.md, settings. ✅
2. LangChain: ChatOpenAI + @tool tools + mock fake chat model. ✅
3. LangGraph: StateGraph QE loop, safety rules in nodes, checkpointer. ✅
4. Deep-agent pattern: planner to-do list + parallel journey sub-agents via Send. ✅
5. Human in the loop: interrupt before report; `--auto-approve`. ✅
6. LangSmith: tracing; eval dataset + experiment (recall, precision, false alarms); one real eval. ✅
7. GitHub Actions CI (mock) + README. ✅

## Status (2026-10-14)

All phases done. Mock eval: 100% recall, 0 false alarms. Real evals (gpt-4.1-mini): r1 75% recall,
100% precision, 0 false alarms, $0.044; r2 (after the prompt fix) 75% / 100% / 0, $0.062. BUG-3 was
missed both times. In r2 the heading check was right, but an invalid `to_have_count(lambda)` line made
the test fail on the baseline. Documented as a known limitation; no further tuning (see
evals/history/2026-10-14-real-r2/analysis.md). Parallel Send kept (no issues).
