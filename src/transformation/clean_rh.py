"""Nettoyage et typage des données RH Bronze → Silver (DuckDB)."""

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def clean_rh_to_silver(db_path: str = DEFAULT_DB_PATH) -> int:
    """Nettoie et type les données RH de bronze.rh_raw vers silver.employees.

    Transformations appliquées :
    - Trim des espaces sur nom, prenom, adresse_du_domicile
    - Cast de date_de_naissance et date_d_embauche en DATE
    - Cast de salaire_brut en INTEGER
    - Ajout du flag is_sportif_deplacement (TRUE si déplacement sportif)
    - Ajout de la colonne _transformed_at (timestamp UTC)

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans silver.employees.
    """
    logger.info("Démarrage du nettoyage RH → silver.employees")

    with db_session(db_path) as conn:
        conn.execute(
            """
            CREATE OR REPLACE TABLE silver.employees AS
            SELECT
                id_salarie,
                TRIM(nom)                                 AS nom,
                TRIM(prenom)                              AS prenom,
                CAST(date_de_naissance AS DATE)           AS date_de_naissance,
                bu,
                CAST(date_d_embauche AS DATE)             AS date_d_embauche,
                CAST(salaire_brut AS INTEGER)             AS salaire_brut,
                type_de_contrat,
                CAST(nombre_de_jours_de_cp AS INTEGER)    AS nombre_de_jours_de_cp,
                TRIM(adresse_du_domicile)                 AS adresse_du_domicile,
                moyen_de_deplacement,
                moyen_de_deplacement IN (
                    'Marche/running',
                    'Vélo/Trottinette/Autres'
                )                                         AS is_sportif_deplacement,
                CURRENT_TIMESTAMP                         AS _transformed_at
            FROM bronze.rh_raw
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM silver.employees"
        ).fetchone()[0]

    logger.info("Table silver.employees créée avec %d lignes", row_count)
    return row_count


def main() -> None:
    """Point d'entrée principal : nettoie les données RH vers Silver.

    Returns:
        None
    """
    logger.info("=== Nettoyage RH → Silver ===")
    total = clean_rh_to_silver()
    logger.info("=== Terminé : %d lignes dans silver.employees ===", total)


if __name__ == "__main__":
    main()
