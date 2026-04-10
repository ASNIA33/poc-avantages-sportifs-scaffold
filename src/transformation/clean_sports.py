"""Nettoyage et correction orthographique des sports Bronze → Silver (DuckDB)."""

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Corrections orthographiques connues dans les données source
_SPORT_CORRECTIONS: dict[str, str] = {
    "Runing": "Running",
}


def clean_sports_to_silver(db_path: str = DEFAULT_DB_PATH) -> int:
    """Nettoie les sports de bronze.sports_raw vers silver.sports_activities.

    Transformations appliquées :
    - Correction des fautes d'orthographe (ex : "Runing" → "Running")
    - Trim des espaces sur pratique_d_un_sport
    - Ajout du flag has_sport (TRUE si un sport est déclaré)
    - Ajout de la colonne _transformed_at (timestamp UTC)

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans silver.sports_activities.
    """
    logger.info("Démarrage du nettoyage Sports → silver.sports_activities")

    # Construction dynamique des corrections CASE WHEN
    case_clauses = "\n".join(
        f"            WHEN TRIM(pratique_d_un_sport) = '{src}' THEN '{dst}'"
        for src, dst in _SPORT_CORRECTIONS.items()
    )

    sql = f"""
        CREATE OR REPLACE TABLE silver.sports_activities AS
        SELECT
            id_salarie,
            CASE
{case_clauses}
                ELSE TRIM(pratique_d_un_sport)
            END                                   AS pratique_d_un_sport,
            pratique_d_un_sport IS NOT NULL       AS has_sport,
            CURRENT_TIMESTAMP                     AS _transformed_at
        FROM bronze.sports_raw
    """

    with db_session(db_path) as conn:
        conn.execute(sql)
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM silver.sports_activities"
        ).fetchone()[0]

        # Log des corrections appliquées
        corrections_applied: int = conn.execute(
            "SELECT COUNT(*) FROM silver.sports_activities WHERE pratique_d_un_sport = 'Running'"
        ).fetchone()[0]

    logger.info(
        "Table silver.sports_activities créée avec %d lignes "
        "(%d 'Running' après correction de 'Runing')",
        row_count,
        corrections_applied,
    )
    return row_count


def main() -> None:
    """Point d'entrée principal : nettoie les sports vers Silver.

    Returns:
        None
    """
    logger.info("=== Nettoyage Sports → Silver ===")
    total = clean_sports_to_silver()
    logger.info("=== Terminé : %d lignes dans silver.sports_activities ===", total)


if __name__ == "__main__":
    main()
