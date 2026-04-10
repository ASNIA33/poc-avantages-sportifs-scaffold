"""Calcul de l'éligibilité à la prime sportive (5% du salaire brut) — Silver → Gold."""

from src.utils.config import PRIME_RATE
from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def compute_prime_eligibility(
    db_path: str = DEFAULT_DB_PATH,
    prime_rate: float | None = None,
) -> int:
    """Calcule l'éligibilité à la prime sportive et insère le résultat dans gold.prime_eligibility.

    Règles métier :
    - Périmètre : uniquement les salariés avec is_sportif_deplacement = TRUE (68 salariés)
    - is_eligible = TRUE si la distance domicile-bureau est cohérente (silver.distances.is_valid = TRUE)
    - prime_montant = salaire_brut × prime_rate (0 si non éligible)
    - reason_ineligible = anomaly_reason de silver.distances (NULL si éligible)

    Args:
        db_path: Chemin vers le fichier DuckDB cible.
        prime_rate: Taux de la prime (ex: 0.05 = 5%). Utilise PRIME_RATE si None.

    Returns:
        Nombre de lignes insérées dans gold.prime_eligibility.

    Example:
        >>> n = compute_prime_eligibility()
        >>> n
        68
    """
    rate = prime_rate if prime_rate is not None else PRIME_RATE
    logger.info(
        "Calcul prime sportive (taux=%.2f%%) → gold.prime_eligibility", rate * 100
    )

    with db_session(db_path) as conn:
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE gold.prime_eligibility AS
            SELECT
                e.id_salarie,
                e.nom,
                e.prenom,
                e.bu,
                e.salaire_brut,
                e.moyen_de_deplacement,
                d.distance_km,
                d.mode_transport,
                d.is_valid                                                AS is_eligible,
                CASE
                    WHEN d.is_valid = TRUE
                    THEN ROUND(CAST(e.salaire_brut AS DOUBLE) * {rate}, 2)
                    ELSE 0.0
                END                                                       AS prime_montant,
                d.anomaly_reason                                          AS reason_ineligible,
                CURRENT_TIMESTAMP                                         AS _computed_at
            FROM silver.employees e
            JOIN silver.distances d ON e.id_salarie = d.id_salarie
            WHERE e.is_sportif_deplacement = TRUE
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM gold.prime_eligibility"
        ).fetchone()[0]
        eligible: int = conn.execute(
            "SELECT COUNT(*) FROM gold.prime_eligibility WHERE is_eligible = TRUE"
        ).fetchone()[0]
        total_cost: float = conn.execute(
            "SELECT COALESCE(SUM(prime_montant), 0) FROM gold.prime_eligibility"
        ).fetchone()[0]

    logger.info(
        "gold.prime_eligibility : %d salariés — %d éligibles — coût total %.2f €",
        row_count,
        eligible,
        total_cost,
    )
    return row_count


def main() -> None:
    """Point d'entrée principal : calcule l'éligibilité à la prime sportive.

    Returns:
        None
    """
    logger.info("=== Calcul prime sportive → Gold ===")
    total = compute_prime_eligibility()
    logger.info("=== Terminé : %d lignes dans gold.prime_eligibility ===", total)


if __name__ == "__main__":
    main()
