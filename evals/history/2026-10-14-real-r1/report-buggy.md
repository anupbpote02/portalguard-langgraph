# PortalGuard report: run eval-20261014-150723-real-buggy

- **Release under test:** http://localhost:8000/buggy/
- **Baseline (last good release):** http://localhost:8000/good/
- **Model:** gpt-4.1-mini  |  **Stop reason:** `done`
- **Human approval:** approved by --auto-approve
- Synthetic test data only. Verdicts come from Playwright runs by the harness (release, rerun, baseline), not from the model.

## Summary

| Real bugs | Healed tests | Flaky (not reported) | Needs review | LLM steps | Tokens | Cost | Harness test runs |
|---|---|---|---|---|---|---|---|
| 3 | 0 | 0 | 2 | 32 | 44,655 | $0.0246 | 18 |

## Bugs found

### 1. CHANGED: button "Sign in"  ->  button (no accessible name) (sign-in / main)

- **Type:** accessibility  |  **Journey:** Wrong password shows an error
- **Evidence:**
  - Test `test_wrong_password.py::test_wrong_password_shows_error_and_signin_button_accessible`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 22: TimeoutError: Locator.click: Timeout 5000ms exceeded. | waiting for get_by_role("button", name="Sign in")`
  - Test `test_diff_check_1.py::test_sign_in_button_accessible_name`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 10: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("button", name="Sign in")`
  - Snapshot diff: `sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)`
- **Reproduce:** `python -m pytest runs/eval-20261014-150723-real-buggy/tests/test_wrong_password.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

### 2. REMOVED: heading "Upcoming appointments" [level=2] (dashboard / main)

- **Type:** accessibility  |  **Journey:** See upcoming appointments
- **Evidence:**
  - Test `test_appointments.py::test_appointments_headings_and_list`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 12: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Test `test_diff_check_2.py::test_dashboard_upcoming_appointments_heading`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 11: AssertionError: Locator expected to be visible | Actual value: None | Error: element(s) not found | waiting for get_by_role("heading", name="Upcoming appointments")`
  - Snapshot diff: `dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]`
- **Reproduce:** `python -m pytest runs/eval-20261014-150723-real-buggy/tests/test_appointments.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

### 3. Download lab results PDF journey broken (test_download_pdf.py::test_download_pdf)

- **Type:** functional  |  **Journey:** Download lab results PDF
- **Evidence:**
  - Test `test_download_pdf.py::test_download_pdf`: passed on baseline, failed on release 2/2 runs
  - Failure: `line 12: TimeoutError: Timeout 5000ms exceeded while waiting for event "download"`
  - Snapshot diff: no change in the accessibility tree (functional bug)
- **Reproduce:** `python -m pytest runs/eval-20261014-150723-real-buggy/tests/test_download_pdf.py -p portalguard.fixtures --base-url http://localhost:8000/buggy/`

## Healed tests

None.

## Flaky tests (not reported as bugs)

None.

## Needs human review

- `test_sign_in.py::test_sign_in_page_elements_and_submit` (gave_up): still fails on the baseline after 3 heal attempts. Error: `line 33: Error: value must be a string or regular expression`
- `test_lab_results.py::test_lab_results_frame_heading_and_download_button` (gave_up): still fails on the baseline after 3 heal attempts. Error: `line 19: ValueError: Unsupported type: <class 'playwright.sync_api._generated.FrameLocator'>`

## Plan and journey coverage

- [x] `test_sign_in.py` (sign_in): Check that the sign-in page has the heading 'Sign in', textboxes 'Email' and 'Password', and a button with accessible name 'Sign in'.
- [x] `test_wrong_password.py` (wrong_password): Verify that entering a wrong password on the sign-in page shows an appropriate error message and the sign-in button is accessible.
- [x] `test_appointments.py` (appointments): Confirm that the dashboard page shows the heading 'Welcome, Jordan Rivera' and the 'Upcoming appointments' heading is present.
- [x] `test_lab_results.py` (lab_results): Ensure the lab results frame on the dashboard has the heading 'Lab results' and a button labeled 'Download PDF'.
- [x] `test_download_pdf.py` (download_pdf): Test that clicking the 'Download PDF' button in the lab results frame downloads the lab results PDF file.
- [x] `test_diff_check_1.py` (diff_check): Check that the sign-in page's 'Sign in' button has an accessible name and is not missing it.
- [x] `test_diff_check_2.py` (diff_check): Verify that the dashboard page still contains the 'Upcoming appointments' heading as expected.

- Missing journeys: none

## Snapshot diff (baseline -> release)

- **sign-in / main**
  - `CHANGED: button "Sign in"  ->  button (no accessible name)`
- **dashboard / main**
  - `REMOVED: heading "Upcoming appointments" [level=2]`
- **dashboard / lab-results-frame**
  - `REMOVED: heading "Lab results" [level=1]`
