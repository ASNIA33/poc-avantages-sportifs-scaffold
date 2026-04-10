"""Tests unitaires pour les transformations Bronze → Silver."""

import os

import duckdb
import pytest

from src.ingestion.fetch_distances import fetch_distances_to_bronze
from src.ingestion.generate_strava import generate_strava_data
from src.ingestion.load_excel import load_rh_to_bronze, load_sports_to_bronze
from src.transformation.clean_rh import clean_rh_to_silver
from src.transformation.clean_sports import clean_sports_to_silver
from src.transformation.clean_strava import clean_strava_to_silver
from src.transformation.validate_distances import validate_distances_to_silver

TEST_DB = "/tmp/test_transformation.duckdb"


# ---------------------------------------------------------------------------
# Fixture module-scoped : Bronze chargé + anomalie injectée + Silver calculé
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def silver_db():
    """Crée la DB de test, charge Bronze, injecte une distance anomalique,
    puis exécute toutes les transformations Silver.

    La distance anomalique (walking, 20 km > seuil 15 km) est nécessaire pour
    tester la détection d'anomalies, car les distances haversine en simulation
    sont toutes inférieures aux seuils réels.

    Portée module : la DB est créée une seule fois pour tous les tests.
    """
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    # 1. Chargement Bronze
    load_rh_to_bronze(TEST_DB)
    load_sports_to_bronze(TEST_DB)
    fetch_distances_to_bronze(TEST_DB, api_key="")  # mode simulation forcé
    generate_strava_data(TEST_DB)

    # 2. Injection d'une distance anomalique pour test_distances_anomaly_detection
    #    On choisit le premier salarié "walking" et on force sa distance à 20 km
    #    (> seuil marche/running de 15 km) → déclenchera is_valid = FALSE
    conn = duckdb.connect(TEST_DB)
    first_walking_id = conn.execute(
        "SELECT id_salarie FROM bronze.distances_raw WHERE mode_transport = 'walking' LIMIT 1"
    ).fetchone()[0]
    conn.execute(
        f"UPDATE bronze.distances_raw SET distance_km = 20.0 WHERE id_salarie = {first_walking_id}"
    )
    conn.close()

    # 3. Transformations Silver dans l'ordre (validate_distances dépend de silver.employees)
    clean_rh_to_silver(TEST_DB)
    clean_sports_to_silver(TEST_DB)
    validate_distances_to_silver(TEST_DB)
    clean_strava_to_silver(TEST_DB)

    yield

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _query(sql: str) -> list:
    """Exécute une requête SQL sur la DB de test et retourne les résultats.

    Args:
        sql: Requête SQL à exécuter.

    Returns:
        Liste des tuples résultats.
    """
    conn = duckdb.connect(TEST_DB)
    result = conn.execute(sql).fetchall()
    conn.close()
    return result


# ---------------------------------------------------------------------------
# Tests silver.employees
# ---------------------------------------------------------------------------

@pytest.mark.transformation
def test_employees_row_count() -> None:
    """silver.employees doit contenir exactement 161 lignes."""
    rows = _query("SELECT COUNT(*) FROM silver.employees")
    assert rows[0][0] == 161, f"Attendu 161 lignes, obtenu {rows[0][0]}"


@pytest.mark.transformation
def test_employees_is_sportif() -> None:
    """Exactement 68 salariés doivent avoir is_sportif_deplacement = TRUE."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.employees WHERE is_sportif_deplacement = TRUE"
    )
    assert rows[0][0] == 68, (
        f"Attendu 68 salariés sportifs, obtenu {rows[0][0]}"
    )


@pytest.mark.transformation
def test_employees_no_null_critical() -> None:
    """id_salarie, nom, prenom et salaire_brut ne doivent jamais être nuls."""
    for col in ("id_salarie", "nom", "prenom", "salaire_brut"):
        rows = _query(f"SELECT COUNT(*) FROM silver.employees WHERE {col} IS NULL")
        assert rows[0][0] == 0, f"Trouvé {rows[0][0]} valeur(s) nulle(s) dans '{col}'"


@pytest.mark.transformation
def test_employees_salary_range() -> None:
    """Tous les salaires doivent être compris entre 20 000 et 100 000 €."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.employees WHERE salaire_brut < 20000 OR salaire_brut > 100000"
    )
    assert rows[0][0] == 0, f"Trouvé {rows[0][0]} salaire(s) hors plage [20k, 100k]"


@pytest.mark.transformation
def test_employees_has_transformed_at() -> None:
    """La colonne _transformed_at doit exister et ne contenir aucun null."""
    columns = {
        row[0]
        for row in _query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'silver' AND table_name = 'employees'"
        )
    }
    assert "_transformed_at" in columns, "_transformed_at absente de silver.employees"
    nulls = _query("SELECT COUNT(*) FROM silver.employees WHERE _transformed_at IS NULL")
    assert nulls[0][0] == 0, f"Trouvé {nulls[0][0]} valeur(s) nulle(s) dans _transformed_at"


# ---------------------------------------------------------------------------
# Tests silver.sports_activities
# ---------------------------------------------------------------------------

@pytest.mark.transformation
def test_sports_row_count() -> None:
    """silver.sports_activities doit contenir exactement 161 lignes."""
    rows = _query("SELECT COUNT(*) FROM silver.sports_activities")
    assert rows[0][0] == 161, f"Attendu 161 lignes, obtenu {rows[0][0]}"


@pytest.mark.transformation
def test_sports_no_runing() -> None:
    """Aucune valeur 'Runing' ne doit subsister — doit être corrigée en 'Running'."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.sports_activities WHERE pratique_d_un_sport = 'Runing'"
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} occurrence(s) de 'Runing' non corrigée(s)"
    )


@pytest.mark.transformation
def test_sports_has_sport_flag() -> None:
    """Exactement 95 salariés doivent avoir has_sport = TRUE."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.sports_activities WHERE has_sport = TRUE"
    )
    assert rows[0][0] == 95, f"Attendu 95 salariés avec sport, obtenu {rows[0][0]}"


# ---------------------------------------------------------------------------
# Tests silver.distances
# ---------------------------------------------------------------------------

@pytest.mark.transformation
def test_distances_row_count() -> None:
    """silver.distances doit contenir exactement 68 lignes."""
    rows = _query("SELECT COUNT(*) FROM silver.distances")
    assert rows[0][0] == 68, f"Attendu 68 lignes, obtenu {rows[0][0]}"


@pytest.mark.transformation
def test_distances_anomaly_detection() -> None:
    """Au moins 1 anomalie doit être détectée (is_valid = FALSE).

    Une distance anomalique a été injectée dans la fixture (walking, 20 km > seuil 15 km).
    """
    rows = _query("SELECT COUNT(*) FROM silver.distances WHERE is_valid = FALSE")
    assert rows[0][0] >= 1, (
        f"Aucune anomalie détectée — attendu ≥ 1 (distance 20 km injectée en fixture)"
    )


@pytest.mark.transformation
def test_distances_valid_have_no_reason() -> None:
    """Quand is_valid = TRUE, anomaly_reason doit être NULL."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.distances WHERE is_valid = TRUE AND anomaly_reason IS NOT NULL"
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} ligne(s) valide(s) avec anomaly_reason non nulle"
    )


@pytest.mark.transformation
def test_distances_invalid_have_reason() -> None:
    """Quand is_valid = FALSE, anomaly_reason ne doit pas être NULL."""
    rows = _query(
        "SELECT COUNT(*) FROM silver.distances WHERE is_valid = FALSE AND anomaly_reason IS NULL"
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} ligne(s) invalide(s) sans anomaly_reason"
    )


# ---------------------------------------------------------------------------
# Tests silver.strava_activities
# ---------------------------------------------------------------------------

@pytest.mark.transformation
def test_strava_row_count() -> None:
    """silver.strava_activities doit avoir le même nombre de lignes que bronze.strava_raw."""
    bronze_count = _query("SELECT COUNT(*) FROM bronze.strava_raw")[0][0]
    silver_count = _query("SELECT COUNT(*) FROM silver.strava_activities")[0][0]
    assert silver_count == bronze_count, (
        f"Bronze={bronze_count} lignes, Silver={silver_count} lignes — différence inattendue"
    )


@pytest.mark.transformation
def test_strava_distance_km() -> None:
    """distance_km doit être égal à distance_m / 1000.0 pour toutes les lignes avec distance."""
    rows = _query(
        """
        SELECT COUNT(*) FROM silver.strava_activities
        WHERE distance_m IS NOT NULL
          AND ABS(distance_km - CAST(distance_m AS DOUBLE) / 1000.0) > 0.001
        """
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} ligne(s) où distance_km ≠ distance_m / 1000"
    )


@pytest.mark.transformation
def test_strava_duree_minutes() -> None:
    """duree_minutes doit être égal à temps_ecoule_s / 60.0 pour toutes les lignes."""
    rows = _query(
        """
        SELECT COUNT(*) FROM silver.strava_activities
        WHERE ABS(duree_minutes - CAST(temps_ecoule_s AS DOUBLE) / 60.0) > 0.01
        """
    )
    assert rows[0][0] == 0, (
        f"Trouvé {rows[0][0]} ligne(s) où duree_minutes ≠ temps_ecoule_s / 60"
    )


@pytest.mark.transformation
def test_strava_no_null_required() -> None:
    """id_salarie, date_debut et sport_type ne doivent jamais être nuls dans Silver."""
    for col in ("id_salarie", "date_debut", "sport_type"):
        rows = _query(
            f"SELECT COUNT(*) FROM silver.strava_activities WHERE {col} IS NULL"
        )
        assert rows[0][0] == 0, f"Trouvé {rows[0][0]} valeur(s) nulle(s) dans '{col}'"
