"""Détection et consolidation des anomalies de distance domicile-bureau — Silver → Gold."""

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def detect_distance_anomalies(db_path: str = DEFAULT_DB_PATH) -> int:
    """Extrait les anomalies de distance depuis Silver et les insère dans gold.distance_anomalies.

    Sélectionne les lignes de silver.distances où is_valid = FALSE,
    enrichit avec les informations salariés (silver.employees),
    et logue chaque anomalie en WARNING.

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre d'anomalies insérées dans gold.distance_anomalies.

    Example:
        >>> n = detect_distance_anomalies()
        >>> n >= 0
        True
    """
    logger.info("Détection des anomalies de distance → gold.distance_anomalies")

    with db_session(db_path) as conn:
        conn.execute(
            """
            CREATE OR REPLACE TABLE gold.distance_anomalies AS
            SELECT
                e.id_salarie,
                e.nom,
                e.prenom,
                e.bu,
                e.moyen_de_deplacement,
                e.adresse_du_domicile,
                d.distance_km,
                d.mode_transport,
                d.max_distance_km,
                d.anomaly_reason,
                CURRENT_TIMESTAMP AS _computed_at
            FROM silver.distances d
            JOIN silver.employees e ON d.id_salarie = e.id_salarie
            WHERE d.is_valid = FALSE
            ORDER BY d.distance_km DESC
            """
        )
        anomalies = conn.execute(
            """
            SELECT id_salarie, nom, prenom, distance_km, max_distance_km, anomaly_reason
            FROM gold.distance_anomalies
            """
        ).fetchall()

    for row in anomalies:
        id_sal, nom, prenom, dist, max_dist, reason = row
        logger.warning(
            "ANOMALIE distance — salarié %s (%s %s) : %.2f km > max %.2f km — %s",
            id_sal,
            prenom,
            nom,
            dist,
            max_dist,
            reason,
        )

    logger.info(
        "gold.distance_anomalies : %d anomalie(s) détectée(s)", len(anomalies)
    )
    return len(anomalies)


def main() -> None:
    """Point d'entrée principal : détecte les anomalies de distance.

    Returns:
        None
    """
    logger.info("=== Détection des anomalies de distance → Gold ===")
    total = detect_distance_anomalies()
    logger.info("=== Terminé : %d anomalie(s) dans gold.distance_anomalies ===", total)


if __name__ == "__main__":
    main()
