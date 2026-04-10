"""Nettoyage et typage des activités Strava Bronze → Silver (DuckDB)."""

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def clean_strava_to_silver(db_path: str = DEFAULT_DB_PATH) -> int:
    """Nettoie et type les activités Strava de bronze.strava_raw vers silver.strava_activities.

    Transformations appliquées :
    - Cast de date_debut en TIMESTAMP
    - Cast de distance_m en INTEGER (nullable)
    - Cast de temps_ecoule_s en INTEGER
    - Ajout de distance_km : distance_m / 1000.0 (nullable si distance_m null)
    - Ajout de duree_minutes : temps_ecoule_s / 60.0 (arrondi à 2 décimales)
    - Trim du commentaire
    - Ajout de la colonne _transformed_at (timestamp UTC)

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans silver.strava_activities.
    """
    logger.info("Démarrage du nettoyage Strava → silver.strava_activities")

    with db_session(db_path) as conn:
        conn.execute(
            """
            CREATE OR REPLACE TABLE silver.strava_activities AS
            SELECT
                id,
                id_salarie,
                CAST(date_debut AS TIMESTAMP)             AS date_debut,
                sport_type,
                CAST(distance_m AS INTEGER)               AS distance_m,
                CAST(distance_m / 1000.0 AS DOUBLE)       AS distance_km,
                CAST(temps_ecoule_s AS INTEGER)           AS temps_ecoule_s,
                ROUND(CAST(temps_ecoule_s AS DOUBLE) / 60.0, 2) AS duree_minutes,
                TRIM(commentaire)                         AS commentaire,
                CURRENT_TIMESTAMP                         AS _transformed_at
            FROM bronze.strava_raw
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM silver.strava_activities"
        ).fetchone()[0]
        with_distance: int = conn.execute(
            "SELECT COUNT(*) FROM silver.strava_activities WHERE distance_m IS NOT NULL"
        ).fetchone()[0]

    logger.info(
        "Table silver.strava_activities créée avec %d lignes (%d avec distance)",
        row_count,
        with_distance,
    )
    return row_count


def main() -> None:
    """Point d'entrée principal : nettoie les activités Strava vers Silver.

    Returns:
        None
    """
    logger.info("=== Nettoyage Strava → Silver ===")
    total = clean_strava_to_silver()
    logger.info("=== Terminé : %d lignes dans silver.strava_activities ===", total)


if __name__ == "__main__":
    main()
