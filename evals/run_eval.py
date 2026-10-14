"""Score PortalGuard against the planted bugs, as a LangSmith dataset + experiment.

    python -m evals.run_eval                 # mock chat model ($0), LangSmith experiment if a key is set
    python -m evals.run_eval --real          # gpt-4.1-mini (key from .env)
    python -m evals.run_eval --local         # no LangSmith: same target + evaluators, scored locally (CI)

Dataset "portalguard-releases" has two examples: the buggy release (expected: the 4 planted bugs) and
the good release (expected: nothing). Evaluators are deterministic (evals/scoring.py): recall,
precision, false alarms on good, cost. Runs use --auto-approve and a fresh run folder each.
Writes evals/results.json + results.md. Exit 1 if recall < --min-recall or false alarms > --max-false-alarms.
"""

import argparse
import json
import os
import sys
from datetime import datetime

from evals.scoring import EVALUATORS, match_bugs
from portalguard.config import BUGGY_URL, GOOD_URL, REPO_ROOT
from portalguard.main import ensure_portal, run_qe
from portalguard.tracing import flush, setup_tracing

EVALS_DIR = REPO_ROOT / "evals"
DATASET = "portalguard-releases"
RELEASES = {"buggy": BUGGY_URL, "good": GOOD_URL}


def examples() -> list[dict]:
    expected = json.loads((EVALS_DIR / "expected_bugs.json").read_text(encoding="utf-8"))["bugs"]
    return [{"inputs": {"release": "buggy"}, "outputs": {"expected_bugs": expected}},
            {"inputs": {"release": "good"}, "outputs": {"expected_bugs": []}}]


def ensure_dataset(client) -> str:
    """Create the LangSmith dataset once; reuse it afterwards (same examples every time)."""
    if not client.has_dataset(dataset_name=DATASET):
        dataset = client.create_dataset(DATASET, description="PortalGuard: buggy release (4 planted bugs) and good release")
        client.create_examples(dataset_id=dataset.id, examples=examples())
    return DATASET


def make_target(mock: bool, stamp: str, log: list):
    def target(inputs: dict) -> dict:
        release = inputs["release"]
        print(f"  running the agent on {release} ...", flush=True)
        state = run_qe(RELEASES[release], mock=mock, auto_approve=True,
                       run_id=f"eval-{stamp}-{'mock' if mock else 'real'}-{release}")
        usage = state.get("usage", {})
        outputs = {"bugs": state.get("bugs", []), "stop_reason": state.get("stop_reason"),
                   "steps": usage.get("steps", 0), "tokens": usage.get("tokens", 0),
                   "cost_usd": usage.get("cost_usd", 0.0), "report": state.get("report"),
                   "healed": sum(1 for r in state.get("tests", {}).values() if r.get("healed"))}
        log.append({"release": release, **outputs})
        return outputs
    return target


def summarize(log: list, mode: str, experiment: str | None, args) -> dict:
    expected = examples()[0]["outputs"]["expected_bugs"]
    buggy = next(r for r in log if r["release"] == "buggy")
    good = next(r for r in log if r["release"] == "good")
    match = match_bugs(buggy["bugs"], expected)
    totals = {"recall": match["recall"], "precision": match["precision"], "type_accuracy": match["type_accuracy"],
              "false_alarms_on_good": len(good["bugs"]),
              "steps": buggy["steps"] + good["steps"], "tokens": buggy["tokens"] + good["tokens"],
              "cost_usd": round(buggy["cost_usd"] + good["cost_usd"], 6), "healed": buggy["healed"] + good["healed"]}
    passed = totals["recall"] >= args.min_recall and totals["false_alarms_on_good"] <= args.max_false_alarms
    return {"mode": mode, "experiment": experiment, "started_at": args.started, "totals": totals,
            "match": match, "good_bug_titles": [b["title"] for b in good["bugs"]],
            "runs": [{k: v for k, v in r.items() if k != "bugs"} | {"bugs": [b["title"] for b in r["bugs"]]} for r in log],
            "gate": {"min_recall": args.min_recall, "max_false_alarms": args.max_false_alarms, "passed": passed}}


def to_markdown(results: dict) -> str:
    t, m = results["totals"], results["match"]
    pct = lambda v: "n/a" if v is None else f"{v * 100:.0f}%"
    lines = [f"# PortalGuard eval ({results['mode']}, {results['started_at']})", ""]
    if results["experiment"]:
        lines += [f"LangSmith experiment: `{results['experiment']}` (dataset `{DATASET}`)", ""]
    lines += ["| Metric | Value |", "|---|---|",
              f"| Recall (planted bugs found) | {pct(t['recall'])} |",
              f"| Precision (reported bugs that are real) | {pct(t['precision'])} |",
              f"| Bug type accuracy | {pct(t['type_accuracy'])} |",
              f"| False alarms on good release | {t['false_alarms_on_good']} |",
              f"| Tests healed | {t['healed']} |",
              f"| LLM steps (buggy + good) | {t['steps']} |",
              f"| Tokens (buggy + good) | {t['tokens']:,} |",
              f"| Cost (buggy + good) | ${t['cost_usd']:.4f} |",
              f"| Gate (recall >= {results['gate']['min_recall']}, false alarms <= {results['gate']['max_false_alarms']}) "
              f"| {'PASS' if results['gate']['passed'] else 'FAIL'} |", "",
              "## Per planted bug", ""]
    lines += [f"- {bug_id}: found as {title}" for bug_id, title in m["found"].items()]
    lines += [f"- {bug_id}: MISSED" for bug_id in m["missed"]]
    lines += [f"- false positive (buggy): {title}" for title in m["false_positives"]]
    lines += [f"- false alarm (good): {title}" for title in results["good_bug_titles"]]
    lines += ["", "Matching is deterministic substring rules from `evals/expected_bugs.json` (no LLM judge).", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", action="store_true", help="gpt-4.1-mini instead of the mock chat model")
    parser.add_argument("--local", action="store_true", help="score locally, no LangSmith dataset/experiment")
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--max-false-alarms", type=int, default=0)
    args = parser.parse_args()
    args.started = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mode = "real" if args.real else "mock"

    print(setup_tracing())
    if args.real and not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set (.env). Use the mock eval or add the key.")
        return 2
    use_langsmith = not args.local and bool(os.environ.get("LANGSMITH_API_KEY"))
    print(f"Portal: {ensure_portal()}. Mode: {mode}. Scoring: {'LangSmith experiment' if use_langsmith else 'local'}.")

    log: list[dict] = []
    target = make_target(not args.real, stamp, log)
    experiment = None
    if use_langsmith:
        from langsmith import Client, evaluate
        client = Client()
        result = evaluate(target, data=ensure_dataset(client), evaluators=EVALUATORS,
                          experiment_prefix=f"portalguard-{mode}", max_concurrency=0,
                          metadata={"mode": mode, "model": "mock" if not args.real else "gpt-4.1-mini"},
                          client=client)
        experiment = result.experiment_name
    else:
        for example in examples():
            outputs = target(example["inputs"])
            for evaluator in EVALUATORS:
                score = evaluator(outputs, example["outputs"])
                print(f"    {example['inputs']['release']}: {score['key']} = {score['score']}")
    flush()

    results = summarize(log, mode, experiment, args)
    (EVALS_DIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8", newline="\n")
    markdown = to_markdown(results)
    (EVALS_DIR / "results.md").write_text(markdown, encoding="utf-8", newline="\n")
    print("\n" + markdown)
    return 0 if results["gate"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
