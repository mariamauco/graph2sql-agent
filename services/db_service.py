"""SQLite metadata extraction, sandbox management, and SQL execution."""

import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any


def extract_schema(db_path):
    """Extract tables, columns, keys, row counts, and safe text samples."""
    def quote(identifier):
        return '"' + identifier.replace('"', '""') + '"'

    sensitive = re.compile(r"password|secret|token|ssn|email|phone|address", re.I)
    tables = []

    # Read SQLite's user tables first, then collect each table's details below.
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        names = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()

        for table_row in names:
            table_name = table_row["name"]
            table_sql_name = quote(table_name)
            columns = []

            for column in connection.execute(f"PRAGMA table_info({table_sql_name})"):
                column_name = column["name"]
                column_data = {
                    "name": column_name,
                    "type": column["type"],
                    "notnull": bool(column["notnull"]),
                    "dflt_value": column["dflt_value"],
                    "pk": bool(column["pk"]),
                    "is_pk": bool(column["pk"]),
                    "is_nullable": not bool(column["notnull"]),
                }
                data_type = (column["type"] or "").upper()
                # Keep small, non-sensitive text domains available to the LLM.
                if data_type.startswith(("TEXT", "VARCHAR", "CHAR")) and not sensitive.search(column_name):
                    values = connection.execute(
                        f"SELECT DISTINCT {quote(column_name)} AS value "
                        f"FROM {table_sql_name} "
                        f"WHERE {quote(column_name)} IS NOT NULL LIMIT 11"
                    ).fetchall()
                    if 0 < len(values) <= 10:
                        column_data["sample_values"] = [value["value"] for value in values]
                columns.append(column_data)

            # SQLite reports foreign keys per table, including their source and target columns.
            foreign_keys = [
                {
                    "ref_table": foreign_key["table"],
                    "from_col": foreign_key["from"],
                    "to_col": foreign_key["to"],
                }
                for foreign_key in connection.execute(
                    f"PRAGMA foreign_key_list({table_sql_name})"
                )
            ]
            row_count = connection.execute(
                f"SELECT COUNT(*) FROM {table_sql_name}"
            ).fetchone()[0]
            tables.append({
                "name": table_name,
                "row_count": row_count,
                "columns": columns,
                "foreign_keys": foreign_keys,
            })

    return {
        "tables": tables,
        "tables_count": len(tables),
        "columns_count": sum(len(table["columns"]) for table in tables),
        "foreign_keys_count": sum(len(table["foreign_keys"]) for table in tables),
    }


def reset_sandbox(db_name, data_dir) -> Path:
    """Reset and return the working copy path for ``db_name``."""
    # Re-copy the untouched source so all working edits are discarded.
    source = Path(data_dir) / f"{db_name}.sqlite"
    working = Path(data_dir) / f"{db_name}_working.sqlite"
    shutil.copy2(source, working)
    return working

def provide_working(db_path):
    source = Path(db_path)
    working = source if source.stem.endswith("_working") else source.with_name(
        f"{source.stem}_working{source.suffix}"
    )
    if not working.exists():
        shutil.copy2(source, working)
    return working

def execute_read_sql(db_path, sql) -> list[dict[str, Any]]:
    """Execute a read-only query against the working database."""
    # Keep this helper read-only; the timeout also limits lock waiting.
    if not sql.lstrip().lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed")
    working = provide_working(db_path)
    with sqlite3.connect(working, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql)]


# Given a source path, execute the mutation on its working-copy database.
def execute_write_sql(db_path, sql) -> int:
    # Restrict this boundary to the mutation types allowed by Edit Mode.
    if not re.match(r"^\s*(INSERT|UPDATE|DELETE|ALTER)\b", sql, re.I):
        raise ValueError("Only INSERT, UPDATE, DELETE, and ALTER queries are allowed")
    working = provide_working(db_path)
    with sqlite3.connect(working, timeout=5) as connection:
        cursor = connection.execute(sql)
        return max(cursor.rowcount, 0)
