# PortalGuard eval (real, 2026-10-14T17:48:51)

LangSmith experiment: `portalguard-real-0c82d801` (dataset `portalguard-releases`)

| Metric | Value |
|---|---|
| Recall (planted bugs found) | 75% |
| Precision (reported bugs that are real) | 100% |
| Bug type accuracy | 100% |
| False alarms on good release | 0 |
| Tests healed | 4 |
| LLM steps (buggy + good) | 56 |
| Tokens (buggy + good) | 88,386 |
| Cost (buggy + good) | $0.0484 |
| Gate (recall >= 1.0, false alarms <= 0) | FAIL |

## Per planted bug

- BUG-1: found as CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)
- BUG-4: found as Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)
- BUG-2: found as REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)
- BUG-3: MISSED

Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).
