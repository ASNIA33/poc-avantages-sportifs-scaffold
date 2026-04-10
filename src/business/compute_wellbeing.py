"""Calcul de l'éligibilité aux jours bien-être (5 jours/an) — Silver → Gold."""

from src.utils.config import WELLBEING_THRESHOLD
from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DAYS_GRANTED: int = 5


def compute_wellbeing_eligibility(
    db_path: str = DEFAULT_DB_PATH,
    threshold: int | None = None,
) -> int:
    """Calcule l'éligibilité aux jours bien-être et insère le résultat dans gold.wellbeing_eligibility.

    Règles métier :
    - Périmètre : tous les salariés (161)
    - activity_count = nombre d'activités dans silver.strava_activities sur les 12 derniers mois
    - is_eligible = TRUE si activity_count >= threshold (défaut 15)
    - days_granted = 5 si éligible, 0 sinon

    Args:
        db_path: Chemin vers le fichier DuckDB cible.
        threshold: Nombre minimum d'activités. Utilise WELLBEING_THRESHOLD si None.

    Returns:
        Nombre de lignes insérées dans gold.wellbeing_eligibility.

    Example:
        >>> n = compute_wellbeing_eligibility()
        >>> n
        161
    """
    seuil = threshold if threshold is not None else WELLBEING_THRESHOLD
    logger.info(
        "Calcul jours bien-être (seuil=%d activités) → gold.wellbeing_eligibility", seuil
    )

    with db_session(db_path) as conn:
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE gold.wellbeing_eligibility AS
            WITH activity_counts AS (
                SELECT
                    id_salarie,
                    COUNT(*) AS activity_count
                FROM silver.strava_activities
                GROUP BY id_salarie
            )
            SELECT
                e.id_salarie,
                e.nom,
                e.prenom,
                e.bu,
                COALESCE(a.activity_count, 0)                             AS activity_count,
                COALESCE(a.activity_count, 0) >= {seuil}                  AS is_eligible,
                CASE
                    WHEN COALESCE(a.activity_count, 0) >= {seuil} THEN {_DAYS_GRANTED}
                    ELSE 0
                END                                                       AS days_granted,
                CURRENT_TIMESTAMP                                         AS _computed_at
            FROM silver.employees e
            LEFT JOIN activity_counts a ON e.id_salarie = a.id_salarie
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM gold.wellbeing_eligibility"
        ).fetchone()[0]
        eligible: int = conn.execute(
            "SELECT COUNT(*) FROM gold.wellbeing_eligibility WHERE is_eligible = TRUE"
        ).fetchone()[0]

    logger.info(
        "gold.wellbeing_eligibility : %d salariés — %d éligibles (%d jours)",
        row_count,
        eligible,
        _DAYS_GRANTED,
    )
    return row_count


def main() -> None:
    """Point d'entrée principal : calcule l'éligibilité aux jours bien-être.

    Returns:
        None
    """
    logger.info("=== Calcul jours bien-être → Gold ===")
    total = compute_wellbeing_eligibility()
    logger.info("=== Terminé : %d lignes dans gold.wellbeing_eligibility ===", total)


if __name__ == "__main__":
    main()
