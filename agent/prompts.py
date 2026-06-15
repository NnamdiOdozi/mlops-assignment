"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = (
    "You are an expert SQL assistant. Given a database schema and a natural language "
    "question, produce a single SQLite SELECT statement that answers the question. "
    "Output ONLY the raw SQL. No explanation, no markdown fences, no commentary."
)

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = (
    "Database schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Write the SQL query."
)


VERIFY_SYSTEM = (
    "You are a SQL result auditor. Given a question, the SQL that was run, and its "
    "execution result, decide whether the result plausibly answers the question.\n\n"
    "Check for these problems:\n"
    "1. Execution error — the query failed.\n"
    "2. Empty result — 0 rows returned when the question clearly expects data.\n"
    "3. Wrong columns — the returned columns do not match what the question asks for.\n\n"
    "Respond with ONLY a JSON object: {\"ok\": true, \"issue\": \"\"} if the result "
    "looks correct, or {\"ok\": false, \"issue\": \"<brief description>\"} if not. "
    "No other text."
)

# Placeholders: {question}, {sql}, {result}
VERIFY_USER = (
    "Question: {question}\n\n"
    "SQL:\n{sql}\n\n"
    "Execution result:\n{result}"
)


REVISE_SYSTEM = (
    "You are a SQL debugger. Given the original question, database schema, a failing "
    "SQL query, its execution result, and the verifier's complaint, produce a "
    "corrected SQLite SELECT statement. Output ONLY the raw SQL. No explanation, "
    "no markdown fences, no commentary."
)

# Placeholders: {schema}, {question}, {sql}, {result}, {issue}
REVISE_USER = (
    "Database schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Previous SQL:\n{sql}\n\n"
    "Execution result:\n{result}\n\n"
    "Problem identified: {issue}\n\n"
    "Write the corrected SQL query."
)
