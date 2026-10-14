# PortalGuard eval (real, 2026-10-14T15:07:23)

LangSmith experiment: `portalguard-real-2ca49ffe` (dataset `portalguard-releases`)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 75% |
| Precision (reported bugs that are real) | 100% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed | 1 |
| LLM steps (buggy + good) | 57 |
| Tokens (buggy + good) | 79,562 |
| Cost (buggy + good) | $0.0441 |
| Gate (recall >= 1.0, false alarms <= 0) | FAIL |

## Per planted bug

- BUG-1: found as CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)
- BUG-2: found as REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)
- BUG-4: found as Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)
- BUG-3: MISSED

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
