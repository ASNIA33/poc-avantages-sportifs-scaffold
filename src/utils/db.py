"""DuckDB connection manager for the POC Avantages Sportifs pipeline."""

import os
from contextlib import contextmanager
from typing import Generator

import duckdb

from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_DB_PATH = os.getenv("DUCKDB_PATH", "data/sports_poc.duckdb")

SCHEMAS = ["bronze", "silver", "gold"]


def get_connection(db_path: str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection and ensure schemas exist.

    Args:
        db_path: Path to the DuckDB file.

    Returns:
        DuckDB connection instance.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = duckdb.connect(db_path)

    for schema in SCHEMAS:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    logger.info("Connected to DuckDB: %s (schemas: %s)", db_path, ", ".join(SCHEMAS))
    return conn


@contextmanager
def db_session(db_path: str = DEFAULT_DB_PATH) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Context manager for DuckDB connections.

    Args:
        db_path: Path to the DuckDB file.

    Yields:
        DuckDB connection instance.
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
        logger.info("DuckDB connection closed")
