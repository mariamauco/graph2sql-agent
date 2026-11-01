"""SQLite metadata extraction, sandbox management, and SQL execution."""

from pathlib import Path
from typing import Any


def extract_schema_metadata(db_identifier) -> dict[str, Any]:
    """Return schema metadata for a database identifier.

    The SQLite extractor and optional SQLAlchemy connector will be implemented here.
    """
    raise NotImplementedError


def reset_sandbox(db_name, data_dir) -> Path:
    """Reset and return the working copy path for ``db_name``."""
    raise NotImplementedError


def execute_read_sql(db_name, sql) -> list[dict[str, Any]]:
    """Execute a read-only query against the working database."""
    raise NotImplementedError


def execute_write_sql(db_name, sql) -> int:
    """Execute a validated mutation against the working database."""
    raise NotImplementedError
