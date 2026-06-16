"""LangGraph agent: text-to-SQL with verify+revise loop.

Graph shape:

    START -> attach_schema -> generate_sql -> execute -> verify
                                                          |
                                              ok=true ----+----> END
                                                          |
                                              ok=false ---+----> revise -> execute -> verify (loop)

Loop is capped at MAX_ITERATIONS total generate/revise calls.

The execute node and the graph wiring are provided. `generate_sql_node` is
filled in as a worked example; you implement `verify`, `revise`, and the
conditional router following the same shape.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from agent import prompts
from agent.config import AGENT_CONFIG, EXPERIMENT_CONFIG
from agent.execution import ExecutionResult, execute_sql
from agent.schema import render_schema

MAX_ITERATIONS = int(AGENT_CONFIG["max_iterations"])
VERIFY_MAX_ROWS = int(AGENT_CONFIG["verify_max_rows"])
VERIFY_MODE = str(AGENT_CONFIG.get("verify_mode", "llm"))  # "llm" or "deterministic"

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.environ.get("VLLM_MODEL", str(AGENT_CONFIG["model"]))
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "not-needed")


@dataclass
class AgentState:
    """State threaded through the graph. Extend with fields you need."""

    question: str
    db_id: str
    schema: str = ""
    sql: str = ""
    execution: ExecutionResult | None = None
    verify_ok: bool = False
    verify_issue: str = ""
    iteration: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


def _make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=VLLM_MODEL,
        base_url=VLLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=float(AGENT_CONFIG["temperature"]),
        max_tokens=int(AGENT_CONFIG["max_tokens"]),
    )

_SHARED_LLM: ChatOpenAI | None = _make_llm() if AGENT_CONFIG.get("reuse_client", True) else None


def llm() -> ChatOpenAI:
    """Return LLM client. Reuses a shared instance when reuse_client=true."""
    if _SHARED_LLM is not None:
        return _SHARED_LLM
    return _make_llm()


# ---- Nodes ------------------------------------------------------------

def _attach_schema(state: AgentState) -> dict:
    """Provided. Render the DB schema once at the start of the run."""
    return {"schema": render_schema(state.db_id)}


def _extract_sql(text: str) -> str:
    """Pull a SQL statement out of an LLM reply, stripping markdown fences/prose.

    Intentionally simple: take the first ```sql ... ``` block if there is one,
    otherwise the whole reply. You may need to harden this for your prompts.
    """
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (fenced.group(1) if fenced else text).strip()


def generate_sql_node(state: AgentState) -> dict:
    """Worked example - the other LLM nodes follow this same shape.

    Build messages from the prompts, call the shared llm(), extract the SQL,
    and return only the state fields you changed. `iteration` is bumped here
    (and in revise) so route_after_verify can enforce MAX_ITERATIONS.

    This node is wired and ready; fill in GENERATE_SQL_SYSTEM / GENERATE_SQL_USER
    in prompts.py to make it produce real queries.
    """
    response = llm().invoke([
        ("system", prompts.GENERATE_SQL_SYSTEM),
        ("user", prompts.GENERATE_SQL_USER.format(
            schema=state.schema,
            question=state.question,
        )),
    ])
    sql = _extract_sql(response.content)
    return {
        "sql": sql,
        "iteration": state.iteration + 1,
        "history": state.history + [{"node": "generate_sql", "sql": sql}],
    }


def execute_node(state: AgentState) -> dict:
    """Provided. Runs the SQL and stores the result."""
    return {"execution": execute_sql(state.db_id, state.sql)}


def _deterministic_verify(state: AgentState) -> tuple[bool, str]:
    """Fast checks that don't need an LLM call. Returns (ok, issue)."""
    ex = state.execution
    sql_upper = state.sql.upper().strip()
    q_lower = state.question.lower()

    # 1. SQL execution error
    if not ex.ok:
        return False, f"Execution error: {ex.error}"

    # 2. Zero rows when question expects data
    if ex.row_count == 0:
        return False, "Empty result when the question clearly expects rows"

    # 3. SELECT * when specific columns were requested
    if sql_upper.startswith("SELECT *") or sql_upper.startswith("SELECT\n*"):
        return False, "SELECT * used — select only the columns the question asks about"

    # 4. Missing aggregation when question implies it
    agg_keywords = {
        "how many": "COUNT",
        "number of": "COUNT",
        "average": "AVG",
        "total": "SUM",
        "highest": "ORDER BY ... DESC LIMIT",
        "lowest": "ORDER BY ... ASC LIMIT",
        "most": "ORDER BY ... DESC LIMIT",
        "least": "ORDER BY ... ASC LIMIT",
    }
    for phrase, expected in agg_keywords.items():
        if phrase in q_lower:
            # Check if the corresponding SQL keyword is present
            if phrase in ("how many", "number of") and "COUNT" not in sql_upper:
                return False, f"Question asks '{phrase}' but SQL has no COUNT"
            if phrase == "average" and "AVG" not in sql_upper:
                return False, f"Question asks 'average' but SQL has no AVG"
            if phrase == "total" and "SUM" not in sql_upper:
                return False, f"Question asks 'total' but SQL has no SUM"
            break  # only check the first matching phrase

    # All checks passed — result looks plausible
    return True, ""


def verify_node(state: AgentState) -> dict:
    """Verify execution result. Uses deterministic checks or LLM based on config."""

    # Deterministic mode: fast checks only, no LLM call
    if VERIFY_MODE == "deterministic":
        ok, issue = _deterministic_verify(state)
        return {"verify_ok": ok, "verify_issue": issue}

    # LLM mode: always run deterministic checks first for obvious failures,
    # then fall through to LLM for semantic verification
    det_ok, det_issue = _deterministic_verify(state)
    if not det_ok:
        return {"verify_ok": False, "verify_issue": det_issue}

    response = llm().invoke([
        ("system", prompts.VERIFY_SYSTEM),
        ("user", prompts.VERIFY_USER.format(
            schema=state.schema,
            question=state.question,
            sql=state.sql,
            result=state.execution.render(max_rows=VERIFY_MAX_ROWS),
        )),
    ])
    text = response.content
    ok = False
    issue = "Could not parse verifier response"
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            raw_ok = parsed.get("ok", False)
            raw_issue = parsed.get("issue", "")
            ok = bool(raw_ok) if isinstance(raw_ok, bool) else False
            issue = str(raw_issue) if isinstance(raw_issue, str) else ""
        except (json.JSONDecodeError, ValueError):
            pass
    return {"verify_ok": ok, "verify_issue": issue}


def _format_previous_attempts(history: list[dict[str, Any]]) -> str:
    sqls = [h["sql"] for h in history if h.get("node") in ("generate_sql", "revise") and h.get("sql")]
    return "\n\n".join(f"Attempt {i+1}:\n{sql}" for i, sql in enumerate(sqls))


def revise_node(state: AgentState) -> dict:
    """Produce a revised SQL query given state.verify_issue and the prior attempt.

    Same shape as generate_sql_node, but the prompt should include the failing
    SQL, its execution result, and the verifier's complaint so the model can fix
    it. Bump the iteration counter the same way generate_sql_node does so the
    loop terminates.

    Return: {"sql": <str>, "iteration": state.iteration + 1, ...}.
    """
    response = llm().invoke([
        ("system", prompts.REVISE_SYSTEM),
        ("user", prompts.REVISE_USER.format(
            schema=state.schema,
            question=state.question,
            previous_attempts=_format_previous_attempts(state.history),
            result=state.execution.render(max_rows=VERIFY_MAX_ROWS),
            issue=state.verify_issue,
        )),
    ])
    sql = _extract_sql(response.content)
    return {
        "sql": sql,
        "iteration": state.iteration + 1,
        "history": state.history + [{"node": "revise", "sql": sql, "issue": state.verify_issue}],
    }


def route_after_verify(state: AgentState) -> str:
    """Conditional router: return "revise" to loop, "end" to terminate.

    Two reasons to end: the verifier was happy (state.verify_ok), or you've hit
    the iteration cap (state.iteration >= MAX_ITERATIONS). Otherwise, revise.
    """
    if state.verify_ok or state.iteration >= MAX_ITERATIONS:
        return "end"
    return "revise"


# ---- Graph wiring -----------------------------------------------------

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("attach_schema", _attach_schema)
    g.add_node("generate_sql", generate_sql_node)
    g.add_node("execute", execute_node)
    g.add_node("verify", verify_node)
    g.add_node("revise", revise_node)

    g.add_edge(START, "attach_schema")
    g.add_edge("attach_schema", "generate_sql")
    g.add_edge("generate_sql", "execute")
    g.add_edge("execute", "verify")
    g.add_conditional_edges(
        "verify",
        route_after_verify,
        {"revise": "revise", "end": END},
    )
    g.add_edge("revise", "execute")
    return g.compile()


graph = build_graph()
