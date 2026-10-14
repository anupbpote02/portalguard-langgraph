"""Safety rule: the baseline is the oracle, and a test that proved a real bug is locked."""

from portalguard.triage import lock_violation, triage_run

GOOD, BUGGY = "http://localhost:8000/good/", "http://localhost:8000/buggy/"
CODE = 'def test_heading(signed_in):\n    expect(signed_in.get_by_role("heading", name="Upcoming appointments")).to_be_visible()\n'
DIFF = {"changes": {"dashboard / main": ['REMOVED: heading "Upcoming appointments" [level=2]']}}
FAIL = {"results": [{"test": "test_appointments.py::test_heading[chromium]", "outcome": "failed",
                     "message": 'line 2: AssertionError | waiting for get_by_role("heading", name="Upcoming appointments")'}]}


def triage(outcomes: dict):
    """outcomes: base_url -> list of outcomes to return, in order."""
    calls = []

    def run_one(base_url, filename, name):
        calls.append(base_url)
        return {"outcome": outcomes[base_url].pop(0), "message": "err"}

    files = {"test_appointments.py": {"journey": "appointments", "code": CODE, "heal_attempts": 0}}
    tests = {}
    triage_run(FAIL, files, tests, DIFF, run_one, GOOD, BUGGY)
    return tests["test_appointments.py::test_heading"], calls


def test_fails_on_baseline_means_broken_test_not_bug():
    record, calls = triage({GOOD: ["failed"]})
    assert record["verdict"] == "broken_test"
    assert calls == [GOOD]  # baseline first, no release reruns wasted


def test_passes_on_baseline_fails_twice_is_real_bug_with_diff_evidence():
    record, calls = triage({GOOD: ["passed"], BUGGY: ["failed"]})
    assert record["verdict"] == "real_bug" and record["category"] == "accessibility"
    assert record["diff_evidence"] == ['dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]']
    assert calls == [GOOD, BUGGY]


def test_passes_on_rerun_is_flaky_not_reported():
    record, _ = triage({GOOD: ["passed"], BUGGY: ["passed"]})
    assert record["verdict"] == "flaky"


def test_bug_proving_test_cannot_be_rewritten():
    weakened = "def test_heading(signed_in):\n    pass\n"
    assert "refused" in lock_violation(CODE, weakened, ["test_heading"])
    assert lock_violation(CODE, CODE + "\n# comment only\n", ["test_heading"]) is None
    assert lock_violation(CODE, CODE + "\ndef test_other(page):\n    pass\n", ["test_heading"]) is None
