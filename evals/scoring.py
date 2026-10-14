"""Deterministic scoring against the planted bugs (no LLM judge). Ported from the original PortalGuard.

A reported bug matches an expected bug if any of its rules holds: plain substring checks on the bug's
snapshot diff lines, or on its journey + failure messages (evals/expected_bugs.json).
"""


def rule_matches(rule: dict, bug: dict) -> bool:
    if "diff" in rule:
        return any(rule["where"] in line and rule["diff"] in line for line in bug["diff_evidence"])
    return bug["journey"] == rule["journey"] and any(rule["error"] in (e or "") for e in bug["errors"])


def match_bugs(reported: list[dict], expected: list[dict]) -> dict:
    """Each reported bug goes to the first expected bug it matches (answer-key order).

    true positive  = matches an expected bug not matched before
    duplicate      = matches an expected bug already matched (not counted as wrong)
    false positive = matches nothing
    """
    found, duplicates, false_positives, type_correct = {}, [], [], 0
    for bug in reported:
        hit = next((e for e in expected if any(rule_matches(r, bug) for r in e["match"])), None)
        if hit is None:
            false_positives.append(bug["title"])
        elif hit["id"] in found:
            duplicates.append(f"{hit['id']}: {bug['title']}")
        else:
            found[hit["id"]] = bug["title"]
            type_correct += bug["category"] == hit["type"]
    return {
        "found": found,
        "missed": [e["id"] for e in expected if e["id"] not in found],
        "duplicates": duplicates,
        "false_positives": false_positives,
        "recall": len(found) / len(expected) if expected else None,
        "precision": (len(found) + len(duplicates)) / len(reported) if reported else (None if not expected else 1.0),
        "type_accuracy": type_correct / len(found) if found else None,
    }


# ---------------------------------------------------------------- LangSmith evaluators
# Signature (outputs, reference_outputs) -> {"key", "score"}; score None = not applicable to this example.

def _match(outputs: dict, reference_outputs: dict) -> dict:
    return match_bugs(outputs.get("bugs", []), reference_outputs.get("expected_bugs", []))


def recall(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "recall", "score": _match(outputs, reference_outputs)["recall"]}


def precision(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "precision", "score": _match(outputs, reference_outputs)["precision"]}


def false_alarms_on_good(outputs: dict, reference_outputs: dict) -> dict:
    """Bugs reported on the good release (where every report is wrong)."""
    if reference_outputs.get("expected_bugs"):
        return {"key": "false_alarms_on_good", "score": None}
    return {"key": "false_alarms_on_good", "score": len(outputs.get("bugs", []))}


def cost_usd(outputs: dict, reference_outputs: dict) -> dict:
    return {"key": "cost_usd", "score": outputs.get("cost_usd", 0.0)}


EVALUATORS = [recall, precision, false_alarms_on_good, cost_usd]
