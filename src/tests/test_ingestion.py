"""Tests unitaires pour l'ingestion Excel → Bronze (DuckDB)."""

import os
import re

import pytest

from src.ingestion.load_excel import load_rh_to_bronze, load_sports_to_bronze

TEST_DB = "/tmp/test_ingestion.duckdb"


@pytest.fixture(autouse=True)
def clean_test_db() -> None:
    """Supprime la base de test avant chaque test pour garantir un état propre."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query(sql: str) -> list:
    """Exécute une requête SQL sur la DB de test et retourne les résultats.

    Args:
        sql: Requête SQL à exécuter.

    Returns:
        Liste des tuples résultats.
    """
    import duckdb
    conn = duckdb.connect(TEST_DB)
    result = conn.execute(sql).fetchall()
    conn.close()
    return result


# ---------------------------------------------------------------------------
# Tests RH
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
def test_load_rh_row_count() -> None:
    """bronze.rh_raw doit contenir exactement 161 lignes."""
    load_rh_to_bronze(TEST_DB)
    rows = _query("SELECT COUNT(*) FROM bronze.rh_raw")
    assert rows[0][0] == 161, f"Attendu 161 lignes, obtenu {rows[0][0]}"


@pytest.mark.ingestion
def test_load_rh_columns_snake_case() -> None:
    """Toutes les colonnes de bronze.rh_raw doivent être en snake_case sans accent."""
    load_rh_to_bronze(TEST_DB)
    columns_raw = _query("SELECT column_name FROM information_schema.columns WHERE table_schema = 'bronze' AND table_name = 'rh_raw'")
    columns = [row[0] for row in columns_raw]

    pattern = re.compile(r"^[a-z0-9_]+$")
    for col in columns:
        assert pattern.match(col), (
            f"Colonne '{col}' n'est pas en snake_case valide (pas d'accent, pas d'espace)"
        )


@pytest.mark.ingestion
def test_load_rh_no_null_id() -> None:
    """La colonne id_salarie de bronze.rh_raw ne doit contenir aucune valeur nulle."""
    load_rh_to_bronze(TEST_DB)
    rows = _query("SELECT COUNT(*) FROM bronze.rh_raw WHERE id_salarie IS NULL")
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} valeur(s) nulle(s) dans id_salarie"


@pytest.mark.ingestion
def test_load_rh_has_ingested_at() -> None:
    """La colonne _ingested_at doit exister et ne contenir aucune valeur nulle."""
    load_rh_to_bronze(TEST_DB)
    columns_raw = _query("SELECT column_name FROM information_schema.columns WHERE table_schema = 'bronze' AND table_name = 'rh_raw'")
    columns = [row[0] for row in columns_raw]
    assert "_ingested_at" in columns, "La colonne _ingested_at est absente de bronze.rh_raw"

    nulls = _query("SELECT COUNT(*) FROM bronze.rh_raw WHERE _ingested_at IS NULL")
    assert nulls[0][0] == 0, f"Trouvé {nulls[0][0]} valeur(s) nulle(s) dans _ingested_at"


# ---------------------------------------------------------------------------
# Tests Sportif
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
def test_load_sports_row_count() -> None:
    """bronze.sports_raw doit contenir exactement 161 lignes."""
    load_sports_to_bronze(TEST_DB)
    rows = _query("SELECT COUNT(*) FROM bronze.sports_raw")
    assert rows[0][0] == 161, f"Attendu 161 lignes, obtenu {rows[0][0]}"


@pytest.mark.ingestion
def test_load_sports_no_null_id() -> None:
    """La colonne id_salarie de bronze.sports_raw ne doit contenir aucune valeur nulle."""
    load_sports_to_bronze(TEST_DB)
    rows = _query("SELECT COUNT(*) FROM bronze.sports_raw WHERE id_salarie IS NULL")
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} valeur(s) nulle(s) dans id_salarie"
