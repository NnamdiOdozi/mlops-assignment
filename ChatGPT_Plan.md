## What the homework is doing

You are building a small **text-to-Structured Query Language system**:

```text
English question
      ↓
Large language model writes SQL
      ↓
SQL runs against a SQLite database
      ↓
Verifier checks whether the result looks sensible
      ↓
If not, revise the SQL and retry
```

Around that agent, you add two kinds of **observability**, meaning tools that show what the system is doing:

* **Prometheus and Grafana** monitor vLLM serving: latency, throughput, queues and key-value cache usage.
* **Langfuse** shows the agent waterfall: generate SQL → execute → verify → perhaps revise.

Finally, you run:

* an **evaluation** measuring whether the generated SQL returns the same rows as the correct SQL;
* a **load test** measuring whether the complete agent meets the service-level objective: 95% of requests below five seconds while handling ten agent requests per second. ([GitHub][1])

The coding scope is fairly contained:

* six prompt templates in `agent/prompts.py`;
* three missing functions in `agent/graph.py`;
* two missing functions in `evals/run_eval.py`;
* one Grafana dashboard;
* a short `REPORT.md`. ([GitHub][2])

---

## Recommended working arrangement

### Use one GitHub fork as the source of truth

Fork the repository into your own GitHub account first. Then clone your fork both locally and on the Nebius virtual machine.

```bash
git clone https://github.com/<your-github-user>/mlops-assignment.git
cd mlops-assignment

git remote add upstream https://github.com/GlebBerjoskin/mlops-assignment.git
# Work directly on main unless you intentionally create another branch.
git checkout main
git push -u origin main
```

On the Nebius virtual machine:

```bash
git clone -b main https://github.com/<your-github-user>/mlops-assignment.git
```

Use **Visual Studio Code Remote SSH** to edit the virtual-machine copy. Keep the local clone mainly for review and backup. Push and pull through GitHub rather than copying files between machines.

### CPU virtual machine

I would use roughly **4 virtual central processing units and 16 gigabytes of memory**. A smaller machine may work if you use Langfuse Cloud, but the supplied self-hosted Langfuse stack contains Langfuse Web, a worker, PostgreSQL, ClickHouse, Redis and MinIO. Langfuse itself recommends at least four cores and 16 gigabytes for a small virtual-machine deployment. ([GitHub][3])

My preferred shortcut is:

```bash
docker compose up -d prometheus grafana
```

Then use **Langfuse Cloud**, avoiding the remaining containers. It will also preserve your traces after you shut down the virtual machine. Langfuse Cloud is officially presented as the easiest managed option. ([Langfuse][4])

---

# Action plan

## Stage 1 — CPU: establish the deliverable structure immediately

Create an empty `REPORT.md` with these headings:

```text
1. Serving configuration
2. Baseline evaluation
3. Agent value
4. Performance experiments
5. Final result
6. What I would do next
```

Also create a checklist containing every required screenshot and result file. The final submission is judged heavily on the evidence and explanation, not merely on whether the target was reached. In particular, the performance diagnosis accounts for 25% of the mark. ([GitHub][1])

Load the BIRD data and confirm the agent server starts, even though its unfinished nodes will not yet work.

---

## Stage 2 — CPU or Token Factory: finish the agent

Nebius Token Factory has the exact `Qwen/Qwen3-30B-A3B-Instruct-2507` family available and provides an OpenAI-compatible interface, so it is a good substitute while writing the prompts and graph logic. ([docs.tokenfactory.nebius.com][5])

Implement this minimal behaviour:

1. `generate_sql` produces only SQL.
2. `execute` runs it.
3. `verify` returns a small JSON object such as:

```json
{"ok": false, "issue": "The query returned zero rows although matching records should exist."}
```

4. `revise` receives the previous SQL, database result and verifier complaint.
5. Stop after three total generation attempts.

Test five questions and deliberately find at least one that enters the revise loop.

**Deliverables produced:** `agent/graph.py`, `agent/prompts.py`, working agent server.

---

## Stage 3 — CPU: finish evaluation and tracing

Implement `eval_one()` and `summarize()` in `evals/run_eval.py`.

The important measurement is not whether the SQL text matches. It is whether both SQL queries return the same rows:

```text
Different SQL text + identical rows = correct
```

First run only two or three questions while debugging. Do not repeatedly run all 30.

Connect Langfuse Cloud, fire ten questions, and capture:

* one trace containing generate → verify → revise;
* the trace list with useful metadata such as model, configuration and experiment name.

The repository already passes metadata into Langfuse through the agent server. ([GitHub][6])

---

## Stage 4 — CPU or cheap test hardware: construct Grafana

Build the dashboard before renting the H100.

Include approximately these panels:

* 50th, 95th and 99th percentile end-to-end latency;
* time to first token;
* time between generated tokens;
* requests running and waiting;
* prompt and generated tokens per second;
* key-value cache percentage;
* request rate.

These metrics are exposed directly by modern vLLM versions. ([vLLM][7])

The numbers from a small model are irrelevant. You are merely confirming that every panel reacts and that the Prometheus queries work.

**Deliverable produced:** `infra/grafana/provisioning/dashboards/serving.json`.

---

## Stage 5 — First H100 session: collect the baseline evidence

Use the official vLLM Docker image rather than installing vLLM and Transformers into the application environment. This isolates the serving dependencies and avoids the Transformers-version conflict mentioned on Discord. Official vLLM documentation recommends the `vllm/vllm-openai` image. ([vLLM][8])

Do not use the floating `latest` tag in your final report. Pin the exact version you tested.

Start with:

* exact required model;
* `max-model-len` around **8,192**, rather than its enormous possible context;
* short maximum output length;
* sensible graphics-processing-unit memory utilisation;
* prefix caching if repeated schema prefixes benefit from it.

Eight thousand one hundred and ninety-two tokens gives room for the stated 1,500–3,000-token prompts plus schema and output. You could later test 4,096 only after measuring actual prompt lengths.

During this session:

1. Run a manual query and capture `vllm_manual_query.png`.
2. Confirm Grafana panels react and capture `grafana_serving.png`.
3. Run the 30-question baseline evaluation once.
4. Capture `grafana_eval_run.png`.
5. Save `results/eval_baseline.json`.
6. Record the initial configuration and results immediately in `REPORT.md`.

Then shut down the GPU.

A baseline of approximately 33% is not automatically a failed submission. The rubric rewards correct evaluation, useful error analysis and evidence that you understand whether revision helps. ([GitHub][1])

---

## Stage 6 — CPU: analyse errors and make one or two targeted improvements

Group failures into a few buckets:

```text
Incorrect table or column
Incorrect join
Incorrect filter
Aggregation error
Empty result
Verifier accepted bad SQL
Verifier rejected good SQL
Revision made the answer worse
```

Use the low-hanging fruit. For example:

```text
Observed:
Verifier accepts SQL errors too easily.

Change:
Make the verifier explicitly reject execution errors before considering plausibility.

Evidence:
Pass rate after one revision rises from X% to Y%.
```

Do not spend days trying to maximise accuracy. The assignment values a clear diagnosis more than a mysterious high score.

---

## Stage 7 — Final H100 session: performance experiments

Avoid beginning with repeated five-minute runs.

Use short probes at increasing load—for example 2, 5, 8 and 10 requests per second—to discover where waiting requests, latency or key-value cache usage begins rising. Then perform the proper five-minute baseline and final run.

At ten agent requests per second for five minutes, the driver sends roughly **3,000 complete agent runs**. Because each run commonly makes two or three model calls, that may become 6,000–9,000 model requests. Short probes prevent wasting GPU time on obviously bad configurations.

For each meaningful change, write:

```text
Saw X → hypothesised Y → changed Z → result W
```

Finish with:

* `grafana_before.png`;
* `grafana_after.png`;
* `results/eval_after_tuning.json`;
* an honest statement of whether the service-level objective was met and whether quality changed.

---

## How I would use the Discord advice

**Token Factory:** excellent for agent construction, prompts, tracing and evaluation-harness testing. It cannot replace the final self-hosted vLLM tests because it does not expose your own vLLM Prometheus metrics, and the README requires final reported performance and quality from the real model endpoint. ([GitHub][1])

**Langfuse Cloud:** a good shortcut. It removes the heaviest part of the CPU infrastructure and preserves traces.

**Official vLLM Docker:** definitely preferable. Keep vLLM isolated from the application’s `uv` environment.

**Latest vLLM:** use a recent release, but pin it. Do not switch versions halfway through your experiments, because you would no longer have a clean before-and-after comparison.

**Reducing `max-model-len`:** sensible. Start conservatively at 8,192 rather than squeezing immediately to 4,096.

## The critical path

```text
Agent works
   ↓
Evaluation works
   ↓
Grafana works
   ↓
First real baseline
   ↓
Error analysis
   ↓
One justified quality improvement
   ↓
One justified serving improvement
   ↓
Final evaluation and report
```

Related concepts worth keeping clear are **execution accuracy**, **95th-percentile latency**, **key-value-cache pressure**, **queue growth**, and **agent trace waterfalls**.

[1]: https://github.com/GlebBerjoskin/mlops-assignment "GitHub - GlebBerjoskin/mlops-assignment · GitHub"
[2]: https://raw.githubusercontent.com/GlebBerjoskin/mlops-assignment/main/agent/graph.py "raw.githubusercontent.com"
[3]: https://raw.githubusercontent.com/GlebBerjoskin/mlops-assignment/main/docker-compose.yml "raw.githubusercontent.com"
[4]: https://langfuse.com/self-hosting?utm_source=chatgpt.com "Self-host Langfuse (Open Source LLM Observability)"
[5]: https://docs.tokenfactory.nebius.com/post-training/models?utm_source=chatgpt.com "Models for fine-tuning in Nebius Token Factory"
[6]: https://raw.githubusercontent.com/GlebBerjoskin/mlops-assignment/main/agent/server.py "raw.githubusercontent.com"
[7]: https://docs.vllm.ai/en/latest/design/metrics/?utm_source=chatgpt.com "Metrics - vLLM Documentation"
[8]: https://docs.vllm.ai/en/stable/deployment/docker/?utm_source=chatgpt.com "Using Docker - vLLM Documentation"


**vLLM should normally be installed and run only on the GPU virtual machine.** Your local machine and CPU virtual machine can run the agent, evaluation code, Langfuse, Prometheus and Grafana without hosting the real model.

Think of it like this:

```text
Your agent = the customer placing an order
vLLM = the kitchen preparing the order
Token Factory = somebody else's hosted kitchen
```

When using Token Factory, you already have a hosted model server. You point your agent to its OpenAI-compatible endpoint; you do not install vLLM yourself.

## Recommended three-stage progression

### 1. Local machine: basic dry run

Run these locally:

```text
Repository and Python environment
BIRD SQLite data
Agent server
Evaluation code
Langfuse tracing
Possibly Prometheus and Grafana containers
```

Use Token Factory or another hosted endpoint for model calls.

This lets you test:

* whether the agent generates and executes SQL;
* whether `verify → revise` works;
* whether Langfuse captures the complete waterfall;
* whether the evaluation runner works;
* whether environment variables and Docker Compose are understood.

You do **not** need vLLM locally.

### 2. CPU virtual machine: rehearsal environment

Move the same repository to the Nebius CPU virtual machine and repeat the setup there. This becomes your rehearsal for:

* Git workflow;
* Docker Compose;
* Secure Shell port forwarding;
* environment variables;
* Langfuse;
* Prometheus and Grafana;
* agent and evaluation services.

Use Token Factory’s `Qwen/Qwen3-30B-A3B-Instruct-2507` endpoint for the agent. Nebius lists that model in Token Factory, so it is a sensible behavioural stand-in for your agent development. ([docs.tokenfactory.nebius.com][1])

The architecture will be:

```text
CPU VM
├── agent server :8001
├── SQLite databases
├── evaluation runner
├── Langfuse
├── Prometheus
└── Grafana
        │
        └── HTTPS request to Token Factory
```

This is enough for **agent tracing**, because Langfuse sits around the agent calls regardless of where the model is hosted. The assignment explicitly permits hosted models for agent logic, tracing and evaluation-harness testing. ([GitHub][2])

## The one observability limitation

Token Factory will not expose its internal vLLM `/metrics` endpoint to your Prometheus instance.

Therefore:

```text
Langfuse observability                   ✅ Works with Token Factory
Agent latency and token information      ✅ Works with Token Factory
Your own vLLM queue metrics              ❌ Not available
Your own key-value-cache metrics         ❌ Not available
Your own vLLM throughput metrics         ❌ Not available
```

Prometheus and Grafana can still start on the CPU virtual machine, but the vLLM panels will have no real serving data.

### Optional CPU-vLLM rehearsal

The assignment suggests an optional CPU-only vLLM using a tiny model such as `Qwen/Qwen3-0.6B`. This would let you test that Prometheus successfully scrapes `/metrics` and that your Grafana panels move. The absolute performance numbers would be meaningless, but the dashboard wiring would be proven. ([GitHub][2])

I would do this only on the **CPU virtual machine**, not on your Windows laptop:

```text
CPU VM
└── tiny Qwen 0.6B through CPU-vLLM
    └── exposes /metrics
        └── Prometheus
            └── Grafana
```

This is optional. Do not spend much time solving CPU-vLLM installation problems. Your higher-value intermediary test is Token Factory plus Langfuse.

---

## 3. GPU virtual machine: install and run the real vLLM server

Move to the GPU only when all of these are ready:

```text
Agent graph works
Prompts are drafted
Evaluation runner works
Langfuse traces work
Grafana dashboard JSON exists
Prometheus configuration exists
vLLM launch configuration has been written
```

Then start the H100 and run vLLM there using its official Docker image. The official image exposes an OpenAI-compatible server and keeps vLLM’s Python, PyTorch, CUDA and Transformers dependencies isolated from your project environment. ([vLLM][3])

The GPU architecture becomes:

```text
H100 VM

vLLM :8000
   ↑
Agent :8001
   ├── SQLite
   └── Langfuse tracing

vLLM /metrics
   ↓
Prometheus :9090
   ↓
Grafana :3000
```

The repository expects the real model to be served on one H100 at `localhost:8000`, with Prometheus scraping vLLM’s `/metrics`. ([GitHub][2])

## Do not `pip install vllm` into the project environment

For the GPU stage, I recommend:

```text
Application dependencies:
uv environment from pyproject.toml

Model server dependencies:
official vLLM Docker container
```

Do not combine them into one Python environment. That is how you avoid the vLLM-versus-Transformers version problem mentioned on Discord.

Your agent should not care whether the model is Token Factory or your own vLLM server. Only its configuration changes:

```env
# Rehearsal
VLLM_BASE_URL=<Token Factory OpenAI-compatible URL>
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_API_KEY=<Token Factory key>
```

Later:

```env
# H100
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_API_KEY=unused
```

The names may differ slightly according to the repository’s `.env.example`, but the switching principle is the same.

## The most efficient sequence

```text
LOCAL
Clone → install dependencies → load data → understand services
   ↓
CPU VM + TOKEN FACTORY
Agent → Langfuse → evaluation harness → Docker/ports rehearsal
   ↓
OPTIONAL CPU-vLLM 0.6B
Confirm Prometheus and Grafana wiring
   ↓
H100 VM + REAL vLLM
Real metrics → baseline evaluation → load tests → tuning → screenshots
```

So the direct answer is:

> **Do not install the real vLLM server locally or on the normal CPU virtual machine. Prepare its launch script and configuration there, but run the official vLLM Docker container when you reach the H100 stage. Optionally use CPU-vLLM with a tiny 0.6-billion-parameter model on the CPU virtual machine purely to rehearse Prometheus and Grafana.**

[1]: https://docs.tokenfactory.nebius.com/post-training/models?utm_source=chatgpt.com "Models for fine-tuning in Nebius Token Factory"
[2]: https://github.com/GlebBerjoskin/mlops-assignment "GitHub - GlebBerjoskin/mlops-assignment · GitHub"
[3]: https://docs.vllm.ai/en/latest/deployment/docker/?utm_source=chatgpt.com "Using Docker - vLLM Documentation"
