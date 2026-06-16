"""Run 10-question eval with a specific Nebius model, calling the graph directly.

Usage:
    uv run python scripts/test_model.py --model "Qwen/Qwen3.5-397B-A17B-fast"
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent.graph as graph_mod
from evals.run_eval import run_sql, matches

EVAL_FILE = Path(__file__).resolve().parent.parent / "evals" / "eval_set.jsonl"
RESULTS_FILE = Path(__file__).resolve().parent.parent / "results" / "interactive_tests.jsonl"
PICK_EVERY = 3
N_QUESTIONS = 10


def run_one(question: dict, gold_sql: str):
    """Run graph directly and score."""
    state = graph_mod.AgentState(question=question["question"], db_id=question["db_id"])
    result = graph_mod.graph.invoke(state)

    # Extract all SQL attempts from history
    attempts = []
    gold_ok, gold_rows, _ = run_sql(question["db_id"], gold_sql)
    for h in result.get("history", []):
        if h.get("node") in ("generate_sql", "revise") and h.get("sql"):
            sql = h["sql"]
            pred_ok, pred_rows, pred_err = run_sql(question["db_id"], sql)
            correct = gold_ok and pred_ok and matches(gold_rows, pred_rows)
            attempts.append({"sql": sql, "correct": correct, "error": pred_err})

    final_sql = result.get("sql", "")
    if final_sql:
        pred_ok, pred_rows, _ = run_sql(question["db_id"], final_sql)
        final_correct = gold_ok and pred_ok and matches(gold_rows, pred_rows)
    else:
        final_correct = False

    return {
        "question": question["question"],
        "db_id": question["db_id"],
        "correct": final_correct,
        "iterations": result.get("iteration", 0),
        "attempts": attempts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    # Override model in graph module
    graph_mod.VLLM_MODEL = args.model
    graph_mod.graph = graph_mod.build_graph()

    run_name = args.run_name or f"model-test-{args.model.split('/')[-1]}"
    print(f"Testing model: {args.model}")

    with open(EVAL_FILE) as f:
        rows = [json.loads(line) for line in f]

    selected = rows[::PICK_EVERY][:N_QUESTIONS]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    correct_count = 0
    revise_count = 0
    fixed_count = 0
    question_results = []

    for i, row in enumerate(selected, 1):
        print(f"\n{'='*60}")
        print(f"Q{i}: {row['question']}")
        print(f"DB:  {row['db_id']}")

        result = run_one(row, row["gold_sql"])
        attempts = result["attempts"]

        had_revise = len(attempts) > 1
        if had_revise:
            revise_count += 1

        for j, a in enumerate(attempts, 1):
            tag = "CORRECT" if a["correct"] else "WRONG"
            print(f"  Attempt {j}: {tag}  SQL: {a['sql'][:120]}")

        if had_revise and not attempts[0]["correct"] and result["correct"]:
            fixed_count += 1
            print("  Revision: FIXED")

        if result["correct"]:
            correct_count += 1

        print(f"  Final: {'CORRECT' if result['correct'] else 'WRONG'} | Iterations: {result['iterations']}")
        question_results.append(result)

    total = len(selected)
    print(f"\n{'='*60}")
    print(f"MODEL: {args.model}")
    print(f"SUMMARY ({timestamp}, run: {run_name})")
    print(f"  Correct: {correct_count}/{total} ({correct_count/total*100:.0f}%)")
    print(f"  Revise triggered: {revise_count}/{total}")
    print(f"  Fixed by revision: {fixed_count}")

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": timestamp,
        "run_name": run_name,
        "model": args.model,
        "total": total,
        "correct": correct_count,
        "accuracy": correct_count / total if total else 0,
        "revise_triggered": revise_count,
        "fixed_by_revision": fixed_count,
        "per_question": [
            {"question": r["question"], "db_id": r["db_id"], "correct": r["correct"], "iterations": r["iterations"]}
            for r in question_results
        ],
    }
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"\nResults appended to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
