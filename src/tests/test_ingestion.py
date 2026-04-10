"""Tests unitaires pour l'ingestion Excel → Bronze (DuckDB)."""

import os
import re

import pytest

from src.ingestion.load_excel import load_rh_to_bronze, load_sports_to_bronze
from src.ingestion.generate_strava import generate_strava_data

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


# ---------------------------------------------------------------------------
# Fixture Strava
# ---------------------------------------------------------------------------

@pytest.fixture
def strava_db() -> None:
    """Peuple la base de test avec RH, Sportif et données Strava simulées.

    Doit être utilisé après clean_test_db (autouse), qui garantit une DB propre.
    """
    load_rh_to_bronze(TEST_DB)
    load_sports_to_bronze(TEST_DB)
    generate_strava_data(TEST_DB)


# ---------------------------------------------------------------------------
# Tests Strava
# ---------------------------------------------------------------------------

@pytest.mark.ingestion
def test_strava_generation_row_count(strava_db) -> None:
    """bronze.strava_raw doit contenir plus de 1000 lignes."""
    rows = _query("SELECT COUNT(*) FROM bronze.strava_raw")
    count = rows[0][0]
    assert count > 1000, f"Attendu > 1000 lignes, obtenu {count}"


@pytest.mark.ingestion
def test_strava_columns(strava_db) -> None:
    """bronze.strava_raw doit contenir les 7 colonnes attendues."""
    columns_raw = _query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'bronze' AND table_name = 'strava_raw'"
    )
    columns = {row[0] for row in columns_raw}
    expected = {"id", "id_salarie", "date_debut", "sport_type", "distance_m", "temps_ecoule_s", "commentaire"}
    assert expected == columns, f"Colonnes attendues : {expected}, obtenues : {columns}"


@pytest.mark.ingestion
def test_strava_no_null_required(strava_db) -> None:
    """id_salarie, date_debut et sport_type ne doivent jamais être nuls."""
    for col in ("id_salarie", "date_debut", "sport_type"):
        rows = _query(f"SELECT COUNT(*) FROM bronze.strava_raw WHERE {col} IS NULL")
        assert rows[0][0] == 0, f"Trouvé {rows[0][0]} valeur(s) nulle(s) dans '{col}'"


@pytest.mark.ingestion
def test_strava_distance_positive(strava_db) -> None:
    """Quand distance_m n'est pas nulle, elle doit être strictement positive."""
    rows = _query(
        "SELECT COUNT(*) FROM bronze.strava_raw WHERE distance_m IS NOT NULL AND distance_m <= 0"
    )
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} distance(s) nulle ou négative(s)"


@pytest.mark.ingestion
def test_strava_duration_positive(strava_db) -> None:
    """temps_ecoule_s doit toujours être strictement positif."""
    rows = _query("SELECT COUNT(*) FROM bronze.strava_raw WHERE temps_ecoule_s <= 0")
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} durée(s) nulle(s) ou négative(s)"


@pytest.mark.ingestion
def test_strava_date_range(strava_db) -> None:
    """Toutes les dates doivent être dans les 12 derniers mois (≤ 365 jours)."""
    rows = _query(
        """
        SELECT COUNT(*) FROM bronze.strava_raw
        WHERE date_debut < (CURRENT_TIMESTAMP - INTERVAL '365 days')
           OR date_debut > CURRENT_TIMESTAMP
        """
    )
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} date(s) hors de la fenêtre 12 mois"


@pytest.mark.ingestion
def test_strava_only_sportifs(strava_db) -> None:
    """Tous les id_salarie dans strava_raw doivent exister dans sports_raw avec un sport non nul."""
    rows = _query(
        """
        SELECT COUNT(*) FROM bronze.strava_raw s
        WHERE NOT EXISTS (
            SELECT 1 FROM bronze.sports_raw sr
            WHERE sr.id_salarie = s.id_salarie
              AND sr.pratique_d_un_sport IS NOT NULL
        )
        """
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} salarié(s) dans strava_raw absent(s) ou sans sport dans sports_raw"
    )
