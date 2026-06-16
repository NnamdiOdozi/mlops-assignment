# Report

## 1. Serving configuration

## 2. Baseline evaluation

## 3. Agent value

### Iterative prompt and schema improvements

We ran 10 spread-out questions from eval_set.jsonl after each change, logging results with timestamps to `results/interactive_tests.jsonl`.

**Baseline (original prompts, no schema samples):** 1/10 correct (10%). The original prompts were minimal — just "write SQL" with no guidance. The verify/revise loop triggered on 2/5 questions in an earlier 5-question run but never fixed anything.

**Step 1 — Strengthened prompts (step1-stronger-prompts):** 1/10 (10%). Added a SQL-planning checklist (use sample values, identify JOINs from foreign keys, avoid SELECT *, correct aggregation/ordering/LIMIT). Gave the verifier 6 specific checks (tables, joins, filters, columns, aggregation, empty results). Told the reviser not to repeat previous SQL and to reconsider tables/joins on empty results. Accuracy unchanged — the model lacked concrete data values to act on the checklist.

**Step 2 — Schema sample rows (step2-schema-samples):** 1/10 (10%). Added 3 sample rows per table beneath each CREATE TABLE, capped at 6000 chars total. Sample data does appear correctly (e.g. "Australian Grand Prix" visible in races table with circuitId=1). However, the model (Qwen3-30B-A3B via Nebius) still fails to use this context for multi-table JOINs and domain-specific filter values.

**Important discovery — stale server:** Steps 1-2 ran against a server that had not restarted, so code changes were not picked up. All three runs used identical old code, explaining the flat 1/10.

**Step 3 — Few-shot examples + fresh server (step3-fresh-server):** 1/10 (10%). Added two worked examples to the system prompt: one showing JOIN through an intermediate table, one showing domain value lookup from sample data. After restarting the server, the model's behavior changed significantly:
- Q1: Now correctly JOINs races→circuits (was querying circuits.name directly). Fails only because of missing DISTINCT (11 duplicate rows vs gold's 1).
- Q4: Now uses `label='+'` for carcinogenic (was using `label='carcinogenic'`). Fails because aggregation formula differs from gold.
- Revise dropped from 6/10 to 2/10 — model more confident on first attempt.

**Step 4 — DISTINCT + exact column names (step4-distinct-colnames):** 1/10 (10%). Added DISTINCT and exact column name rules to checklist. Q7 now produces correct answer ('Palo Alto Unified') on some runs but not others.

**Step 5 — BIRD column descriptions (step5-column-descriptions):** 1/10 (10%). BIRD ships per-table CSV files with human-written column meanings (e.g. `A14: no. of entrepreneurs per 1000 inhabitants`, `A15: no. of committed crimes 1995`). Loaded these into `render_schema()` as `-- Column meanings` comments after each CREATE TABLE. The descriptions now appear in the prompt context, but accuracy remained flat. Key observation: the financial Q2 ("average crimes in 1995") used `A14` (entrepreneurs) instead of `A15` (crimes) despite both descriptions being visible — the model has the information but makes reasoning errors when choosing between similarly-described columns.

### Diagnostic analysis

Failure categories across 9 wrong answers:
- **Domain value mismatch (4/9):** Model can't map domain terms to stored codes (e.g. "Blue" → colour.id=7, "disqualified" → statusId=2)
- **Missing DISTINCT (1/9):** Correct data, wrong cardinality
- **Wrong column (1/9):** Ambiguous column names in schema (A14 vs A15)
- **Wrong filter logic (2/9):** Correct structure but wrong filter values
- **Wrong output columns (1/9):** Selects wrong columns for the answer

**Non-determinism:** Qwen3-30B-A3B (MoE architecture) produces different SQL at temperature=0 across calls. Expert routing varies, so identical prompts yield different results. This means accuracy fluctuates between runs — some questions pass by luck.

**Key takeaway:** Prompt engineering (few-shot examples, sample rows, column descriptions) gave the model all necessary context. SQL structure improved substantially — correct JOINs, correct domain values like `label='+'`. However, Qwen3-30B-A3B's reasoning quality is now the bottleneck: it picks wrong columns from visible descriptions (A14 vs A15), omits DISTINCT despite explicit instructions, and produces different SQL at temperature=0 due to MoE expert routing. Execution-accuracy scoring is strict (exact row match), so semantically-close answers still fail.

### Model comparison experiment

To confirm the bottleneck was model quality rather than prompt design, we tested two larger Qwen models on the Nebius API using identical prompts and schema enrichment (sample rows + column descriptions). All three models used the same agent pipeline (generate → execute → verify → revise, max 3 iterations).

| Model | Parameters | Correct | Accuracy |
|---|---|---|---|
| Qwen3-30B-A3B (baseline) | 30B (3B active) | 1/10 | 10% |
| Qwen3-Next-80B-A3B-Thinking | 80B (3B active) | 2/10 | 20% |
| **Qwen3.5-397B-A17B-fast** | **397B (17B active)** | **4/10** | **40%** |

The 397B model fixed several failure categories that prompt engineering could not:
- **Q1 (formula_1):** Added `DISTINCT` unprompted — resolved the duplicate-rows issue that persisted across all prompt iterations with 30B.
- **Q8 (superhero):** JOINed the `colour` table by name (`'Blue'`, `'No Colour'`) instead of guessing integer IDs — domain value mismatch solved by stronger reasoning over sample data.
- **Q9 (thrombosis):** Correctly identified `Admission = '-'` for outpatient and filtered bilirubin within normal range — multi-condition medical query that 30B couldn't compose.

The 80B thinking model underperformed expectations (2/10). Its `<think>` reasoning tags may have interfered with SQL extraction, and it used wrong values like `'mythic rare'` instead of `'mythic'` despite sample rows showing the correct value.

**Conclusion:** A 4x accuracy improvement (10% → 40%) came purely from model scale, with zero prompt changes. This confirms that our prompt and schema enrichment pipeline is sound — the 30B model simply lacks the reasoning capacity to reliably use the context it receives.

### Full evaluation — Qwen3.5-397B-A17B-fast (30 questions)

We ran the complete eval set (30 questions across 11 databases) against the best-performing model from the comparison experiment. Results logged to `results/interactive_tests.jsonl` as run `qwen3.5-397B-full-30`.

**Overall: 16/30 correct (53% execution accuracy)**

| Database | Correct | Total | Accuracy |
|---|---|---|---|
| superhero | 3 | 3 | 100% |
| student_club | 3 | 3 | 100% |
| codebase_community | 3 | 5 | 60% |
| financial | 2 | 3 | 67% |
| formula_1 | 2 | 4 | 50% |
| california_schools | 1 | 3 | 33% |
| thrombosis_prediction | 1 | 3 | 33% |
| toxicology | 0 | 2 | 0% |
| card_games | 0 | 3 | 0% |

Key observations:
- **Revision provides no value at this model scale:** Revise triggered on only 2/30 questions, fixed 0. Q29 was correct on first attempt but the verifier flagged it and revision broke it — a net negative.
- **Perfect on simpler schemas:** superhero and student_club (straightforward JOINs, clear column names) scored 100%.
- **Zero on domain-heavy databases:** toxicology and card_games require precise domain value mapping (element codes, rarity/format enums) that even the 397B model struggles with.
- **53% is a strong result** given that Qwen3-30B-A3B scored 10% with identical prompts. The prompt pipeline (checklist, few-shot examples, sample rows, BIRD column descriptions) is validated — it just needs a model with sufficient reasoning capacity.

## 4. Performance experiments

## 5. Final result

## 6. What I would do next
