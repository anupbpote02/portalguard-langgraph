# Real eval r2 (gpt-4.1-mini, 2026-10-14): analysis

LangSmith experiment `portalguard-real-8eee9e05`, dataset `portalguard-releases`. First real run
after the r1 prompt fix (commit `0dc297a`). The code and prompts were not changed after this run.

| Metric | r1 | r2 |
|---|---|---|
| Recall | 75% (BUG-3 missed) | 75% (BUG-3 missed) |
| Precision | 100% | 100% |
| False alarms on good release | 0 | 0 |
| LLM steps | 57 (buggy 32, good 25) | 65 (buggy 30, good 35) |
| Tokens | 79,562 | 111,099 |
| Cost | $0.0441 | $0.0619 (buggy $0.0254, good $0.0365) |

## What the fix changed

The lab results sub-agent did what the prompt fix asked (see `buggy-tests/test_lab_results.py`):

- It tested the `REMOVED: heading "Lab results"` line as baseline behavior
  (`# Check the "Lab results" heading is present on the baseline`). r1 had skipped it.
- It used `expect()` on a Locator inside the frame (`frame_locator(...).locator("body")`) and the
  right `labResults` key (`test`). r1 called `expect()` on a FrameLocator and used `name`.

On the buggy release, that heading check fails exactly where the bug is.

## Why BUG-3 was still missed

The last line of the test is `expect(rows).to_have_count(lambda c: c >= 1)`. `to_have_count` only
takes an int, so the test fails on the **baseline** with
`TypeError: ... Object of type function is not JSON serializable`. I confirmed this by rerunning the
test on the good release: the heading check passes there and only that line fails.

Triage worked as designed. A test that fails on the baseline is a broken test, not evidence of a
bug. The heal tasks gave the model that baseline error 3 times, and the model kept the lambda every
time, so the verdict was gave_up and the test went to "Needs human review". No false bug was
reported. This is a different mistake from r1, in a different line of the test.

The planner's two diff checks went to the sign-in button and the appointments heading again, so no
other test covered the iframe heading.

## Known limitation (documented, not tuned)

The rules for this round said not to tune further. As a result:

1. **One bad assertion makes a whole journey test useless.** When a single invalid line fails on the
   baseline, the heading check in the same test can't prove anything, and the heals didn't remove
   the line. Ideas for later: one assertion per test for diff checks, guaranteed diff checks for
   iframe diffs, or an AST check that rejects non-literal `to_have_count` arguments.
2. **The report quotes the wrong error for gave_up tests.** "Needs human review" shows the
   *release* error (the missing heading, line 10) next to "still fails on the baseline", but the
   baseline error is the `to_have_count` TypeError (line 22). It's stored in the triage record as
   `baseline_error`. Fix: show `baseline_error` for broken_test/gave_up (one line in `report.py`).

Other changes from r1: in r2, `test_sign_in.py` proved BUG-1 (in r1 it gave up after its heals),
and the wrong-password test healed in 1 attempt.
