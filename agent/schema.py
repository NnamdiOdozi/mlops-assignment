"""Schema-rendering helper (provided complete).

Loads the schema directly from sqlite and renders quoted CREATE TABLE
text suitable for prompt context. Identifiers are always double-quoted
so reserved-word table/column names (e.g. `order`) don't break either
the PRAGMA introspection here or the SQL the model emits later.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data" / "bird"
DESC_DIR = ROOT / "data" / "bird" / "dev_20240627" / "dev_databases"


def db_path(db_id: str) -> Path:
    return DB_DIR / f"{db_id}.sqlite"


def _q(ident: str) -> str:
    """Double-quote a SQL identifier, escaping any embedded quotes."""
    return '"' + ident.replace('"', '""') + '"'


def _load_column_descriptions(db_id: str, table_name: str) -> dict[str, str]:
    """Load BIRD column descriptions CSV for a table. Returns {col_name: description}."""
    # Try common CSV name variants (lowercase, original case)
    for name in (table_name, table_name.lower(), table_name.replace('"', '')):
        csv_path = DESC_DIR / db_id / "database_description" / f"{name}.csv"
        if csv_path.exists():
            break
    else:
        return {}
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            descs = {}
            for row in reader:
                col = row.get("original_column_name", "").strip()
                desc = row.get("column_description", "").strip()
                val_desc = row.get("value_description", "").strip()
                if not col or not desc:
                    continue
                # Skip if description is same as column name (no new info)
                if desc.lower() == col.lower():
                    continue
                entry = desc
                if val_desc and val_desc.lower() not in ("not useful", ""):
                    entry += f" ({val_desc})"
                descs[col] = entry
            return descs
    except Exception:
        return {}


def render_schema(db_id: str, sample_rows: int | None = None,
                   sample_max_chars: int | None = None,
                   cell_max_chars: int | None = None) -> str:
    sr = sample_rows if sample_rows is not None else int(os.environ.get("SCHEMA_SAMPLE_ROWS", "3"))
    smc = sample_max_chars if sample_max_chars is not None else int(os.environ.get("SCHEMA_SAMPLE_MAX_CHARS", "6000"))
    cmc = cell_max_chars if cell_max_chars is not None else int(os.environ.get("SAMPLE_CELL_MAX_CHARS", "80"))
    return _render_schema_cached(db_id, sr, smc, cmc)


@lru_cache(maxsize=32)
def _render_schema_cached(db_id: str, sample_rows: int,
                           sample_max_chars: int, cell_max_chars: int) -> str:
    path = db_path(db_id)
    if not path.exists():
        raise FileNotFoundError(f"DB {db_id} not found at {path}. Did you run scripts/load_data.py?")

    parts: list[str] = [f"-- Database: {db_id}"]
    total_sample_chars = 0

    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        for t in tables:
            parts.append(f"\nCREATE TABLE {_q(t)} (")
            col_lines: list[str] = []
            col_names: list[str] = []
            for _cid, name, ctype, notnull, _dflt, pk in conn.execute(f"PRAGMA table_info({_q(t)})"):
                line = f"  {_q(name)} {ctype}"
                if pk:
                    line += " PRIMARY KEY"
                if notnull and not pk:
                    line += " NOT NULL"
                col_lines.append(line)
                col_names.append(name)
            for fk in conn.execute(f"PRAGMA foreign_key_list({_q(t)})"):
                col_lines.append(
                    f"  FOREIGN KEY ({_q(fk[3])}) REFERENCES {_q(fk[2])}({_q(fk[4])})"
                )
            parts.append(",\n".join(col_lines))
            parts.append(");")

            # Add column descriptions from BIRD metadata
            col_descs = _load_column_descriptions(db_id, t)
            if col_descs:
                desc_lines = [f"-- Column meanings for {_q(t)}:"]
                for col in col_names:
                    if col in col_descs:
                        desc_lines.append(f"--   {col}: {col_descs[col]}")
                if len(desc_lines) > 1:  # has at least one description
                    parts.append("\n".join(desc_lines))

            if total_sample_chars < sample_max_chars and sample_rows > 0:
                try:
                    rows = conn.execute(f"SELECT * FROM {_q(t)} LIMIT {sample_rows}").fetchall()
                    if rows:
                        sample_lines = [f"-- Sample rows from {_q(t)}:"]
                        sample_lines.append(f"-- {' | '.join(col_names)}")
                        for row in rows:
                            cells = []
                            for c in row:
                                s = str(c) if c is not None else "NULL"
                                if len(s) > cell_max_chars:
                                    s = s[:cell_max_chars] + "..."
                                cells.append(s)
                            sample_lines.append(f"-- {' | '.join(cells)}")
                        sample_text = "\n".join(sample_lines)
                        parts.append(sample_text)
                        total_sample_chars += len(sample_text)
                except Exception:
                    pass
    return "\n".join(parts)


def available_dbs() -> list[str]:
    if not DB_DIR.exists():
        return []
    return sorted(p.stem for p in DB_DIR.glob("*.sqlite"))
