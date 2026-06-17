"""Run 10 spread-out eval questions, score with eval_one, log timestamped results."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import CONFIG, CONFIG_PATH  # noqa: E402
from evals.run_eval import eval_one  # noqa: E402

EVAL_FILE = Path(__file__).resolve().parent.parent / "evals" / "eval_set.jsonl"
RESULTS_FILE = Path(__file__).resolve().parent.parent / "results" / "interactive_tests.jsonl"
PICK_EVERY = 3  # from 30 questions, picks indices 0,3,6,...,27 = 10 questions
N_QUESTIONS = 10


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-url", default="http://localhost:8001/answer")
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    with open(EVAL_FILE) as f:
        rows = [json.loads(line) for line in f]

    selected = rows[::PICK_EVERY][:N_QUESTIONS]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    revise_count = 0
    fixed_count = 0
    broken_count = 0
    correct_count = 0
    question_results = []

    for i, row in enumerate(selected, 1):
        print(f"\n{'='*60}")
        print(f"Q{i}: {row['question']}")
        print(f"DB:  {row['db_id']}")

        result = eval_one(row, args.agent_url)

        attempts = result.get("iteration_results", [])
        had_revise = len(attempts) > 1
        if had_revise:
            revise_count += 1

        for a in attempts:
            tag = "CORRECT" if a["correct"] else "WRONG"
            print(f"  Attempt {a['attempt']}: {tag}  SQL: {a['sql'][:100]}")
            if a.get("execution_error"):
                print(f"    error: {a['execution_error']}")

        first_correct = attempts[0]["correct"] if attempts else False
        final_correct = result["correct"]

        if had_revise:
            if not first_correct and final_correct:
                status = "FIXED by revision"
                fixed_count += 1
            elif first_correct and not final_correct:
                status = "BROKEN by revision"
                broken_count += 1
            elif final_correct:
                status = "stayed correct"
            else:
                status = "stayed wrong"
            print(f"  Revision: {status}")

        if final_correct:
            correct_count += 1

        print(f"  Final: {'CORRECT' if final_correct else 'WRONG'} | Iterations: {result['iterations']}")
        question_results.append(result)

    total = len(selected)
    print(f"\n{'='*60}")
    print(f"SUMMARY ({timestamp}, run: {args.run_name or 'unnamed'})")
    print(f"  Correct: {correct_count}/{total} ({correct_count/total*100:.0f}%)")
    print(f"  Revise triggered: {revise_count}/{total}")
    print(f"  Fixed by revision: {fixed_count}")
    print(f"  Broken by revision: {broken_count}")

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": timestamp,
        "run_name": args.run_name,
        "config_path": str(CONFIG_PATH),
        "config": CONFIG,
        "total": total,
        "correct": correct_count,
        "accuracy": correct_count / total if total else 0,
        "revise_triggered": revise_count,
        "fixed_by_revision": fixed_count,
        "broken_by_revision": broken_count,
        "per_question": [
            {
                "question": r["question"],
                "db_id": r["db_id"],
                "correct": r["correct"],
                "iterations": r["iterations"],
            }
            for r in question_results
        ],
    }
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"\nResults appended to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
