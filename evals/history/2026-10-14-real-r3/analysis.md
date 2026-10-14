# Real eval r3 (gpt-4.1-mini, 2026-10-14): analysis

LangSmith experiment `portalguard-real-0c82d801` (dataset `portalguard-releases`): scores and outputs.
Full QE traces: LangSmith project **`portalguard-langgraph`**, root runs
`portalguard-qe eval-20261014-174851-real-buggy` (137 spans, 29 LLM calls) and
`...-real-good` (113 spans, 27 LLM calls). Same prompts as r2; the only code change was trace routing
(below).

| Metric | r1 | r2 | r3 |
|---|---|---|---|
| Recall | 75% | 75% | 75% (BUG-3 missed) |
| Precision | 100% | 100% | 100% |
| False alarms on good release | 0 | 0 | 0 |
| LLM steps | 57 | 65 | 56 (buggy 29, good 27) |
| Tokens | 79,562 | 111,099 | 88,386 |
| Cost | $0.0441 | $0.0619 | $0.0484 (buggy $0.0248, good $0.0236) |

## Tracing change in this round

r2's traces only went to the experiment's own project (`portalguard-real-8eee9e05`), because
`langsmith.evaluate()` nests the target's work there. Now the eval target runs the agent inside
`tracing_context(project_name=LANGSMITH_PROJECT, parent=False)` (`portalguard/tracing.in_project`).
Each QE run is then a root trace in `portalguard-langgraph`, the same as a CLI run. The experiment keeps
the outputs (including `run_id` and `trace_project`, which link to the trace) and the evaluator scores.
I checked this through the LangSmith API, first with a $0 mock run (`portalguard-mock-f3347c04`) and
then with this run.

## Why BUG-3 was still missed (a third, different way)

1. **The diff check covered it, but its first assertion failed first.** The planner did target the
   iframe diff this time. `buggy-tests/test_diff_check_2.py` checks both removed headings:
   "Upcoming appointments" (line 12), then "Lab results" inside the frame (line 17, correct). On the
   buggy release, line 12 fails first, so pytest never reaches line 17. Triage takes diff evidence
   from the failing line, so the test proved BUG-2 only.
2. **The lab results journey test skipped the heading.** Its goal asked for the heading, but the test
   checks the Download button and a made-up `.lab-result-item` class (the page uses a table). It
   failed on the baseline, triage said broken_test, all 3 heals kept the selector, and it gave up
   into "Needs human review". No false bug.

## Known limitation (documented, not tuned)

In three real runs, the agent wrote a correct BUG-3 check twice (r2 journey test, r3 diff check).
Both times another assertion in the same test hid it: an invalid assertion that failed on the baseline
in r2, and an earlier assertion that failed on the release in r3. The shared cause is several
assertions per test with pytest stopping at the first failure. Likely fixes, none applied: one diff
line per diff check (or `expect.soft`-style collection of every failure), and a guaranteed diff check
for each iframe diff.
