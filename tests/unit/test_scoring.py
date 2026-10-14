"""Eval scoring: deterministic matching of reported bugs against the answer key."""

import json

from evals.scoring import false_alarms_on_good, match_bugs, precision, recall
from portalguard.config import REPO_ROOT

EXPECTED = json.loads((REPO_ROOT / "evals" / "expected_bugs.json").read_text(encoding="utf-8"))["bugs"]


def bug(title, category="accessibility", journey=None, diff=(), errors=()):
    return {"title": title, "category": category, "journey": journey, "diff_evidence": list(diff), "errors": list(errors)}


ALL_FOUR = [
    bug("sign in", diff=['sign-in / main: CHANGED: button "Sign in"  ->  button (no accessible name)']),
    bug("appointments", diff=['dashboard / main: REMOVED: heading "Upcoming appointments" [level=2]']),
    bug("lab results", diff=['dashboard / lab-results-frame: REMOVED: heading "Lab results" [level=1]']),
    bug("download", "functional", "Download lab results PDF", errors=['TimeoutError: waiting for event "download"']),
]


def test_all_four_found():
    result = match_bugs(ALL_FOUR, EXPECTED)
    assert result["recall"] == 1.0 and result["precision"] == 1.0 and result["type_accuracy"] == 1.0


def test_duplicate_is_not_a_false_positive_and_noise_is():
    result = match_bugs(ALL_FOUR[:1] * 2 + [bug("made up", diff=["dashboard / main: ADDED: text"])], EXPECTED)
    assert result["recall"] == 0.25
    assert len(result["duplicates"]) == 1 and result["false_positives"] == ["made up"]
    assert result["missed"] == ["BUG-2", "BUG-3", "BUG-4"]


def test_evaluators_split_buggy_and_good():
    buggy_ref, good_ref = {"expected_bugs": EXPECTED}, {"expected_bugs": []}
    assert recall({"bugs": ALL_FOUR}, buggy_ref)["score"] == 1.0
    assert false_alarms_on_good({"bugs": ALL_FOUR}, buggy_ref)["score"] is None
    assert false_alarms_on_good({"bugs": ALL_FOUR[:1]}, good_ref)["score"] == 1
    assert precision({"bugs": []}, good_ref)["score"] is None
