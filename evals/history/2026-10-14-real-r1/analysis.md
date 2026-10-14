# Real eval r1 (gpt-4.1-mini, 2026-10-14): analysis

LangSmith experiment `portalguard-real-2ca49ffe`, dataset `portalguard-releases`.

| Metric | Value |
|---|---|
| Recall | 75% (BUG-1, BUG-2, BUG-4 found; BUG-3 missed) |
| Precision | 100% |
| False alarms on good release | 0 |
| LLM steps | 57 (buggy 32, good 25) |
| Tokens | 79,562 |
| Cost | $0.0441 (buggy $0.0246, good $0.0195) |

## Why BUG-3 ("Lab results" heading removed, inside the iframe) was missed

The harness did the right thing: no false report, and the broken test went to "Needs human review".
The lab results sub-agent made two mistakes (see `buggy-tests/test_lab_results.py`):

1. It read the diff line `REMOVED: heading "Lab results"` as the spec and wrote
   `# The baseline shows the heading "Lab results" was removed, so we do NOT check for it`.
   It wrote the test for the release instead of the baseline.
2. It called `expect(frame_locator)` (Playwright rejects a FrameLocator) and used `result['name']` (the
   key is `test`), so the test failed on the baseline. Triage said broken_test, but all 3 heals kept
   the same mistake, so the verdict was gave_up.

The planner's two diff checks were for the sign-in button and the appointments heading, so nothing
else covered the iframe heading.

`test_sign_in.py` also gave up (`to_have_url` with a non-string). BUG-1 was still caught by
`test_wrong_password.py` (it clicks "Sign in") and by a diff check.

## Fix (commit after this run)

Sub-agent prompt: REMOVED diff lines exist on the baseline and should be tested; `labResults` keys;
`expect()` only on a Locator or Page, never a frame_locator; `to_have_url` takes a string or regex.
Planner prompt: diff checks may target iframe diffs. Not re-evaluated with the real model yet
(this phase called for one real eval).
