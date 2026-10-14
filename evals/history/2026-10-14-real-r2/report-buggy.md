# PortalGuard report: run eval-20261014-173322-real-buggy

- **Release under test:** http://localhost:8000/buggy/
- **Baseline (last good release):** http://localhost:8000/good/
- **Model:** gpt-4.1-mini  |  **Stop reason:** `done`
- **Human approval:** approved by --auto-approve
- Synthetic test data only. Verdicts come from Playwright runs by the harness (release, rerun, baseline), not from the model.

## Summary

| Real bugs | Healed tests | Flaky (not reported) | Needs review | LLM steps | Tokens | Cost | Harness test runs |
|---|---|---|---|---|---|---|---|
| 3 | 1 | 0 | 1 | 30 | 46,768 | $0.0254 | 15 |

## Bugs found

### 1. CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)

- **Type:** accessibility  |  **Journey:** Sign in
- **Evidence:**
  - Test `test_sign_in.py::test_sign_in_journey`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 18: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("button", name="Sign in")`
  - Test `test_diff_check_1.py::test_sign_in_button_accessible_name`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 12: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("button", name="Sign in")`
  - Snapshot diff: `sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)`
- **Reproduce:** `python -m pytest runs/eval-20261014-173322-real-buggy/tests/test_sign_in.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

### 2. REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)

- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_appointments.py::test_upcoming_appointments_and_list`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 8: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Test `test_diff_check_2.py::test_upcoming_appointments_heading`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 7: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Snapshot diff: `dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]`
- **Reproduce:** `python -m pytest runs/eval-20261014-173322-real-buggy/tests/test_appointments.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

### 3. Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)

- **Type:** functional  |  **Journey:** Download lab results PDF
- **Evidence:**
  - Test `test_download_pdf.py::test_download_pdf`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 13: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest runs/eval-20261014-173322-real-buggy/tests/test_download_pdf.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

## Healed tests

| Test | Attempts | Original error (on baseline) | Now |
|---|---|---|---|
| `test_wrong_password.py::test_wrong_password_shows_error` | 1/3 | `line 22: TimeoutError: Locator.click: Timeout 5000ms exceeded. \| waiting for get_by_role("button", name="Sign in")` | passes on release |

## Flaky tests (not reported as bugs)

None.

## Needs human review

- `test_lab_results.py::test_lab_results_frame_contents` (gave_up): still fails on the baseline after 3 heal attempts. Error: `line 10: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for locator("#lab-results-frame").content_frame.locator("body").get_by_role("heading", name="Lab results")`

## Plan and journey coverage

- [x] `test_sign_in.py` (sign_in): Check that the sign-in page has the heading 'Sign in' and the 'Sign in' button is present and accessible by name.
- [x] `test_wrong_password.py` (wrong_password): Verify that entering a wrong password on the sign-in page shows an appropriate error message.
- [x] `test_appointments.py` (appointments): Confirm that the dashboard page displays the heading 'Upcoming appointments'.
- [x] `test_lab_results.py` (lab_results): Ensure the lab results frame on the dashboard shows the heading 'Lab results' and the 'Download PDF' button.
- [x] `test_download_pdf.py` (download_pdf): Test that clicking the 'Download PDF' button in the lab results frame downloads the lab results PDF file.
- [x] `test_diff_check_1.py` (diff_check): Check that the 'Sign in' button on the sign-in page has an accessible name and is not missing it.
- [x] `test_diff_check_2.py` (diff_check): Verify that the 'Upcoming appointments' heading is present on the dashboard page.

- Missing journeys: none

## Snapshot diff (baseline -> release)

- **sign-in / main**
  - `CHANGED: button "Sign in"  ->  button (no accessible name)`
- **dashboard / main**
  - `REMOVED: heading "Upcoming appointments" [level=2]`
- **dashboard / lab-results-frame**
  - `REMOVED: heading "Lab results" [level=1]`
