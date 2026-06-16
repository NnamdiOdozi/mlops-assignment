"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"
MAX_ATTEMPTS = 3
AGENT_TIMEOUT_SECONDS = 120.0


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''."""
    if rows is None:
        return None
    return sorted(tuple("" if c is None else str(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

def _attempt_sqls(agent_response: dict) -> list[str]:
    """Extract the initial and revised SQL statements from agent history."""
    attempts = [
        item["sql"]
        for item in agent_response.get("history", [])
        if isinstance(item, dict)
        and item.get("node") in {"generate_sql", "revise"}
        and item.get("sql")
    ]

    final_sql = agent_response.get("sql", "")

    if final_sql and (not attempts or attempts[-1] != final_sql):
        attempts.append(final_sql)

    return attempts[:MAX_ATTEMPTS]

def eval_one(question: dict, agent_url: str, run_name: str = "") -> dict:
    """Score one question using execution accuracy for every SQL attempt."""
    db_id = question["db_id"]
    gold_sql = question["gold_sql"]

    gold_ok, gold_rows, gold_error = run_sql(db_id, gold_sql)

    started = time.monotonic()

    try:
        response = httpx.post(
            agent_url,
            json={
                "question": question["question"],
                "db": db_id,
                "tags": {"run_name": run_name},
            },
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        agent_response = response.json()

        if not isinstance(agent_response, dict):
            raise ValueError(
                "Agent returned a non-object JSON response"
            )

        request_error = None

    except Exception as exc:  # noqa: BLE001
        agent_response = {}
        request_error = f"{type(exc).__name__}: {exc}"

    latency_seconds = time.monotonic() - started

    iteration_results: list[dict] = []

    for attempt_index, sql in enumerate(
        _attempt_sqls(agent_response)
    ):
        pred_ok, pred_rows, pred_error = run_sql(db_id, sql)

        correct = (
            gold_ok
            and pred_ok
            and matches(gold_rows, pred_rows)
        )

        iteration_results.append({
            "iteration": attempt_index,
            "attempt": attempt_index + 1,
            "sql": sql,
            "execution_ok": pred_ok,
            "execution_error": pred_error,
            "row_count": (
                len(pred_rows)
                if pred_rows is not None
                else None
            ),
            "correct": correct,
        })

    final_correct = (
        iteration_results[-1]["correct"]
        if iteration_results
        else False
    )

    final_sql = agent_response.get("sql", "")

    iterations = int(
        agent_response.get(
            "iterations",
            len(iteration_results),
        )
        or 0
    )

    # Row previews (capped at 5)
    gold_preview = [list(r) for r in (gold_rows or [])[:5]] if gold_rows else []
    pred_ok, pred_rows, _ = run_sql(db_id, final_sql) if final_sql else (False, None, None)
    pred_preview = [list(r) for r in (pred_rows or [])[:5]] if pred_rows else []

    return {
        "question": question["question"],
        "db_id": db_id,
        "gold_sql": gold_sql,
        "gold_execution_ok": gold_ok,
        "gold_execution_error": gold_error,
        "gold_row_count": (
            len(gold_rows)
            if gold_rows is not None
            else None
        ),
        "gold_rows_preview": gold_preview,
        "pred_rows_preview": pred_preview,
        "agent_history": agent_response.get("history", []),
        "agent_sql": final_sql,
        "agent_ok": bool(
            agent_response.get("ok", False)
        ),
        "request_error": request_error,
        "agent_error": agent_response.get("error"),
        "iterations": iterations,
        "latency_seconds": latency_seconds,
        "iteration_results": iteration_results,
        "correct": final_correct,
        "execution_match": final_correct,
    }


def summarize(results: list[dict]) -> dict:
    """Calculate final and per-iteration execution accuracy."""
    total = len(results)

    final_passes = sum(
        bool(result.get("correct", False))
        for result in results
    )

    pass_counts: dict[str, int] = {}
    pass_rates: dict[str, float] = {}

    for attempt_index in range(MAX_ATTEMPTS):
        passed = 0

        for result in results:
            attempts = result.get(
                "iteration_results",
                [],
            )

            if not attempts:
                continue

            # Carry the last available result forward when
            # the agent stopped before this attempt.
            carried_result = attempts[
                min(attempt_index, len(attempts) - 1)
            ]

            passed += bool(
                carried_result.get("correct", False)
            )

        key = str(attempt_index)

        pass_counts[key] = passed
        pass_rates[key] = (
            passed / total
            if total
            else 0.0
        )

    average_iterations = (
        sum(
            int(result.get("iterations", 0))
            for result in results
        )
        / total
        if total
        else 0.0
    )

    return {
        "total_questions": total,
        "passed": final_passes,
        "failed": total - final_passes,
        "execution_accuracy": (
            final_passes / total
            if total
            else 0.0
        ),
        "overall_pass_rate": (
            final_passes / total
            if total
            else 0.0
        ),
        "per_iteration_pass_rates": pass_rates,
        "per_iteration_pass_counts": pass_counts,
        "average_iterations": average_iterations,
        "agent_request_errors": sum(
            bool(result.get("request_error"))
            for result in results
        ),
        "agent_reported_errors": sum(
            bool(result.get("agent_error"))
            for result in results
        ),
        "gold_execution_errors": sum(
            not result.get("gold_execution_ok", False)
            for result in results
        ),
        "fixed_by_revision": sum(
            1 for r in results
            if len(r.get("iteration_results", [])) > 1
            and not r["iteration_results"][0].get("correct")
            and r.get("correct")
        ),
        "broken_by_revision": sum(
            1 for r in results
            if len(r.get("iteration_results", [])) > 1
            and r["iteration_results"][0].get("correct")
            and not r.get("correct")
        ),
        "unchanged_correct": sum(
            1 for r in results
            if (len(r.get("iteration_results", [])) <= 1 and r.get("correct"))
            or (len(r.get("iteration_results", [])) > 1
                and r["iteration_results"][0].get("correct")
                and r.get("correct"))
        ),
        "unchanged_wrong": sum(
            1 for r in results
            if (len(r.get("iteration_results", [])) <= 1 and not r.get("correct"))
            or (len(r.get("iteration_results", [])) > 1
                and not r["iteration_results"][0].get("correct")
                and not r.get("correct"))
        ),
    }


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    parser.add_argument("--run-name", default="")
    args = parser.parse_args()

    if args.out is None:
        args.out = ROOT / "results" / f"eval_{timestamp}.json"

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url, run_name=args.run_name))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "timestamp": timestamp,
        "run_name": args.run_name,
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
