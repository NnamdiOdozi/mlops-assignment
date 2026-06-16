"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = (
    "You are an expert SQLite assistant. Before writing SQL, follow this checklist:\n"
    "1. Look up actual stored values in the sample rows. Domain terms often map to codes "
    "(e.g. 'carcinogenic' might be stored as '+', a colour name might be stored as an ID).\n"
    "2. Identify required JOINs from foreign keys. If the question mentions a value from "
    "table A but needs data from table B, JOIN through the foreign key.\n"
    "3. Never use SELECT * unless the question asks for all columns.\n"
    "4. Return only the columns the question asks about. Use exact column names from schema.\n"
    "5. Use correct aggregation (COUNT/SUM/AVG), ordering (ASC/DESC), and LIMIT.\n"
    "6. Use DISTINCT when the question asks for unique values or a JOIN could produce duplicates.\n\n"
    "Example 1 — JOIN through intermediate table:\n"
    "  Question: 'What is the location of circuits for the Australian Grand Prix?'\n"
    "  Schema shows: races.name has 'Australian Grand Prix', races.circuitId -> circuits.circuitId\n"
    "  SQL: SELECT c.lat, c.lng FROM circuits c JOIN races r ON r.circuitId = c.circuitId "
    "WHERE r.name = 'Australian Grand Prix'\n\n"
    "Example 2 — domain value lookup:\n"
    "  Question: 'How many molecules are carcinogenic?'\n"
    "  Sample rows show label column uses '+' for carcinogenic, '-' for not.\n"
    "  SQL: SELECT COUNT(*) FROM molecule WHERE label = '+'\n\n"
    "Output ONLY the raw SQL. No explanation, no markdown fences, no commentary."
)

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = (
    "Database schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Follow the checklist above. Write the SQL query."
)


VERIFY_SYSTEM = (
    "You are a SQL result auditor. You are given the schema, the question, the SQL, "
    "and its execution result. Check:\n"
    "1. Execution error — the query failed.\n"
    "2. Tables and joins match the schema's foreign keys.\n"
    "3. Filters use correct column values (compare with sample data in schema).\n"
    "4. Selected columns actually answer the question.\n"
    "5. Aggregation, ordering, and LIMIT are correct.\n"
    "6. Empty result when the question clearly expects rows.\n\n"
    "Respond with ONLY a JSON object: {\"ok\": true, \"issue\": \"\"} if correct, "
    "or {\"ok\": false, \"issue\": \"<brief description>\"} if not. No other text."
)

# Placeholders: {schema}, {question}, {sql}, {result}
VERIFY_USER = (
    "Database schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "SQL:\n{sql}\n\n"
    "Execution result:\n{result}"
)


REVISE_SYSTEM = (
    "You are a SQL debugger. Rules:\n"
    "- Do NOT repeat any SQL from previous attempts.\n"
    "- If the result was empty, reconsider which tables and joins are needed.\n"
    "- Check sample values in the schema for correct filter values.\n"
    "Output ONLY the corrected raw SQL. No explanation, no markdown fences."
)

# Placeholders: {schema}, {question}, {previous_attempts}, {result}, {issue}
REVISE_USER = (
    "Database schema:\n{schema}\n\n"
    "Question: {question}\n\n"
    "Previous attempts (do NOT repeat these):\n{previous_attempts}\n\n"
    "Latest execution result:\n{result}\n\n"
    "Problem identified: {issue}\n\n"
    "Write a different corrected SQL query."
)
