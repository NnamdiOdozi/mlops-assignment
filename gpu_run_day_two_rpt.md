# GPU Run Day 2 — Performance Report
**Config:** fp8 weights, max_num_seqs=64, Qwen3-30B-A3B-Instruct-2507

## Load Test Results

| RPS | Duration | OK | HTTP Err | Timeouts | Client Err | p50 | p95 |
|-----|----------|----|----------|----------|------------|-----|-----|
| 10  | 60s      | 521 | 78      | 0        | 1          | 0.48s | 2.12s |
| 20  | 300s     | 5218 | 773   | 7        | 2          | 0.63s | 2.16s |
| 25  | 300s     | 6541 | 956   | 2        | 1          | 0.74s | 2.48s |
| 30  | 300s     | 6642 | 1157  | 26       | 1175       | 39.6s | 105s  |

**Sustainable ceiling: 25 RPS.** At 30 RPS the system saturates — p50 jumps to 39.6s, p95 to 105s, and the driver achieves only ~25 RPS against the 30 RPS target.

## Eval Under Load (25 RPS, 600s background load)

- **Execution accuracy: 46.7%** (14/30 questions passed)
- Agent errors: 0 — all failures were incorrect SQL, not runtime errors
- Avg iterations per question: 1.23

## Key Files

| Purpose | File |
|---------|------|
| 25 RPS load test | `results/load_rps25_300_fp8w_64.json` |
| 25 RPS during eval (600s) | `results/load_rps25_600_fp8w_64_during_eval.json` |
| Eval under load | `results/eval_under_load_25rps.json` |
| 20 RPS load test | `results/load_rps20_300_fp8w_64_v2.json` |
| 30 RPS load test | `results/load_rps30_300_fp8w_64_v2.json` |
| Grafana screenshot (25 RPS) | `screenshots/grafana_after.png` |
