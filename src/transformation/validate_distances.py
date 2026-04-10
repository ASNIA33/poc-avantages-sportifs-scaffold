"""Validation des distances domicile-bureau Bronze → Silver avec détection d'anomalies."""

from src.utils.config import BIKE_MAX_KM, WALK_MAX_KM
from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def validate_distances_to_silver(db_path: str = DEFAULT_DB_PATH) -> int:
    """Valide les distances de bronze.distances_raw vers silver.distances.

    Effectue un JOIN avec silver.employees pour récupérer le moyen_de_deplacement,
    calcule le seuil applicable (WALK_MAX_KM ou BIKE_MAX_KM), détermine si la
    distance est valide et génère un message d'anomalie si elle ne l'est pas.

    Les seuils sont lus depuis src.utils.config (paramètres dynamiques).

    Transformations appliquées :
    - Ajout de max_distance_km : seuil applicable selon mode_transport
    - Ajout de is_valid : TRUE si distance_km <= max_distance_km
    - Ajout de anomaly_reason : NULL si valide, description sinon
    - Ajout de _transformed_at (timestamp UTC)

    Prérequis : silver.employees doit exister (appeler clean_rh_to_silver en amont).

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans silver.distances.
    """
    logger.info(
        "Validation des distances → silver.distances "
        "(seuils : marche %.1f km, vélo %.1f km)",
        WALK_MAX_KM,
        BIKE_MAX_KM,
    )

    sql = f"""
        CREATE OR REPLACE TABLE silver.distances AS
        SELECT
            d.id_salarie,
            d.adresse_domicile,
            d.distance_km,
            d.mode_transport,
            e.moyen_de_deplacement,
            d.source,
            CASE d.mode_transport
                WHEN 'walking'   THEN {WALK_MAX_KM}
                WHEN 'bicycling' THEN {BIKE_MAX_KM}
                ELSE {BIKE_MAX_KM}
            END                                           AS max_distance_km,
            d.distance_km <= CASE d.mode_transport
                WHEN 'walking'   THEN {WALK_MAX_KM}
                WHEN 'bicycling' THEN {BIKE_MAX_KM}
                ELSE {BIKE_MAX_KM}
            END                                           AS is_valid,
            CASE
                WHEN d.mode_transport = 'walking'
                     AND d.distance_km > {WALK_MAX_KM}
                    THEN 'Distance '
                         || CAST(ROUND(d.distance_km, 1) AS VARCHAR)
                         || ' km dépasse le seuil de {WALK_MAX_KM} km pour '
                         || e.moyen_de_deplacement
                WHEN d.mode_transport = 'bicycling'
                     AND d.distance_km > {BIKE_MAX_KM}
                    THEN 'Distance '
                         || CAST(ROUND(d.distance_km, 1) AS VARCHAR)
                         || ' km dépasse le seuil de {BIKE_MAX_KM} km pour '
                         || e.moyen_de_deplacement
                ELSE NULL
            END                                           AS anomaly_reason,
            CURRENT_TIMESTAMP                             AS _transformed_at
        FROM bronze.distances_raw d
        JOIN silver.employees e ON d.id_salarie = e.id_salarie
    """

    with db_session(db_path) as conn:
        conn.execute(sql)
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM silver.distances"
        ).fetchone()[0]
        anomaly_count: int = conn.execute(
            "SELECT COUNT(*) FROM silver.distances WHERE is_valid = FALSE"
        ).fetchone()[0]

    logger.info(
        "Table silver.distances créée avec %d lignes (%d anomalie(s) détectée(s))",
        row_count,
        anomaly_count,
    )
    if anomaly_count > 0:
        logger.warning(
            "%d salarié(s) avec distance hors seuil — voir silver.distances WHERE is_valid = FALSE",
            anomaly_count,
        )
    return row_count


def main() -> None:
    """Point d'entrée principal : valide les distances vers Silver.

    Returns:
        None
    """
    logger.info("=== Validation distances → Silver ===")
    total = validate_distances_to_silver()
    logger.info("=== Terminé : %d lignes dans silver.distances ===", total)


if __name__ == "__main__":
    main()
