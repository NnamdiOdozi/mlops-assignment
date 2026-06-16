"""Post 5 spread-out eval questions to /answer and show traces."""
import json
import sys
import requests

EVAL_FILE = "evals/eval_set.jsonl"
ENDPOINT = "http://localhost:8001/answer"
PICK_EVERY = 6  # from 30 questions, picks indices 0,6,12,18,24

with open(EVAL_FILE) as f:
    rows = [json.loads(line) for line in f]

selected = rows[::PICK_EVERY][:5]
revise_count = 0

for i, row in enumerate(selected, 1):
    print(f"\n{'='*60}")
    print(f"Q{i}: {row['question']}")
    print(f"DB:  {row['db_id']}")
    print(f"Gold SQL: {row['gold_sql'][:80]}...")

    resp = requests.post(ENDPOINT, json={"question": row["question"], "db": row["db_id"]})
    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code}: {resp.text}")
        continue

    data = resp.json()
    had_revise = any(h.get("node") == "revise" for h in data.get("history", []))
    if had_revise:
        revise_count += 1

    print(f"  Iterations: {data['iterations']}")
    print(f"  Revise triggered: {'YES' if had_revise else 'no'}")
    print(f"  OK: {data['ok']}")
    if data.get("error"):
        print(f"  Error: {data['error']}")
    print(f"  Final SQL: {data['sql'][:120]}")
    if data.get("rows") is not None:
        print(f"  Rows returned: {len(data['rows'])}")
        for r in data["rows"][:3]:
            print(f"    {r}")

    # Show history trace
    for h in data.get("history", []):
        node = h.get("node", "?")
        issue = h.get("issue", "")
        sql_preview = h.get("sql", "")[:80]
        print(f"  [{node}] {sql_preview}")
        if issue:
            print(f"    issue: {issue}")

print(f"\n{'='*60}")
print(f"SUMMARY: {revise_count}/5 questions triggered revise")
if revise_count == 0:
    print("WARNING: No revise triggered. Agent may need harder questions or lower verify threshold.")
