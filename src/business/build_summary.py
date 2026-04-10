"""Construction du résumé des coûts par BU et du classement des activités — Gold."""

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_cost_summary(db_path: str = DEFAULT_DB_PATH) -> int:
    """Construit le résumé des coûts par BU dans gold.cost_summary.

    Agrège les coûts de la prime sportive et des jours bien-être par BU,
    plus une ligne TOTAL pour l'ensemble de l'entreprise.

    Structure :
    - bu : identifiant de la BU (Finance, Marketing, R&D, Support, Ventes, TOTAL)
    - nb_prime_eligible : nombre de salariés éligibles à la prime
    - cout_prime_total : somme des montants de prime par BU
    - nb_wellbeing_eligible : nombre de salariés éligibles aux jours bien-être
    - cout_wellbeing_total : nb_wellbeing_eligible × 5 jours × 1 jour moyen (indicateur)
    - nb_total_salaries : effectif total de la BU

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans gold.cost_summary (BU + 1 ligne TOTAL).

    Example:
        >>> n = build_cost_summary()
        >>> n
        6
    """
    logger.info("Construction du résumé des coûts par BU → gold.cost_summary")

    with db_session(db_path) as conn:
        conn.execute(
            """
            CREATE OR REPLACE TABLE gold.cost_summary AS
            WITH bu_prime AS (
                SELECT
                    bu,
                    COUNT(*) FILTER (WHERE is_eligible = TRUE)   AS nb_prime_eligible,
                    SUM(prime_montant)                            AS cout_prime_total
                FROM gold.prime_eligibility
                GROUP BY bu
            ),
            bu_wellbeing AS (
                SELECT
                    bu,
                    COUNT(*) FILTER (WHERE is_eligible = TRUE)   AS nb_wellbeing_eligible,
                    COUNT(*)                                      AS nb_total_salaries
                FROM gold.wellbeing_eligibility
                GROUP BY bu
            ),
            bu_combined AS (
                SELECT
                    w.bu,
                    COALESCE(p.nb_prime_eligible, 0)             AS nb_prime_eligible,
                    COALESCE(p.cout_prime_total, 0.0)            AS cout_prime_total,
                    w.nb_wellbeing_eligible,
                    w.nb_total_salaries,
                    CURRENT_TIMESTAMP                            AS _computed_at
                FROM bu_wellbeing w
                LEFT JOIN bu_prime p ON w.bu = p.bu
            ),
            totals AS (
                SELECT
                    'TOTAL'                                      AS bu,
                    SUM(nb_prime_eligible)                       AS nb_prime_eligible,
                    SUM(cout_prime_total)                        AS cout_prime_total,
                    SUM(nb_wellbeing_eligible)                   AS nb_wellbeing_eligible,
                    SUM(nb_total_salaries)                       AS nb_total_salaries,
                    CURRENT_TIMESTAMP                            AS _computed_at
                FROM bu_combined
            ),
            unioned AS (
                SELECT * FROM bu_combined
                UNION ALL
                SELECT * FROM totals
            )
            SELECT * FROM unioned
            ORDER BY CASE WHEN bu = 'TOTAL' THEN 1 ELSE 0 END, bu
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM gold.cost_summary"
        ).fetchone()[0]
        total_row = conn.execute(
            "SELECT cout_prime_total, nb_wellbeing_eligible FROM gold.cost_summary WHERE bu = 'TOTAL'"
        ).fetchone()

    logger.info(
        "gold.cost_summary : %d lignes — coût prime total %.2f € — %d éligibles jours bien-être",
        row_count,
        total_row[0] if total_row else 0,
        total_row[1] if total_row else 0,
    )
    return row_count


def build_activity_leaderboard(db_path: str = DEFAULT_DB_PATH) -> int:
    """Construit le classement des salariés par nombre d'activités dans gold.activity_leaderboard.

    Classe les salariés selon le nombre d'activités Strava simulées sur 12 mois.
    Inclut tous les salariés (161), ceux sans activité ont activity_count = 0.

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans gold.activity_leaderboard.

    Example:
        >>> n = build_activity_leaderboard()
        >>> n
        161
    """
    logger.info("Construction du classement activités → gold.activity_leaderboard")

    with db_session(db_path) as conn:
        conn.execute(
            """
            CREATE OR REPLACE TABLE gold.activity_leaderboard AS
            WITH counts AS (
                SELECT
                    id_salarie,
                    COUNT(*)                   AS activity_count,
                    MAX(date_debut)            AS derniere_activite
                FROM silver.strava_activities
                GROUP BY id_salarie
            )
            SELECT
                e.id_salarie,
                e.nom,
                e.prenom,
                e.bu,
                COALESCE(c.activity_count, 0) AS activity_count,
                c.derniere_activite,
                RANK() OVER (
                    ORDER BY COALESCE(c.activity_count, 0) DESC
                )                             AS classement,
                CURRENT_TIMESTAMP             AS _computed_at
            FROM silver.employees e
            LEFT JOIN counts c ON e.id_salarie = c.id_salarie
            ORDER BY classement, e.nom, e.prenom
            """
        )
        row_count: int = conn.execute(
            "SELECT COUNT(*) FROM gold.activity_leaderboard"
        ).fetchone()[0]
        top_row = conn.execute(
            """
            SELECT nom, prenom, activity_count
            FROM gold.activity_leaderboard
            WHERE classement = 1
            LIMIT 1
            """
        ).fetchone()

    if top_row:
        logger.info(
            "gold.activity_leaderboard : %d salariés classés — leader : %s %s (%d activités)",
            row_count,
            top_row[1],
            top_row[0],
            top_row[2],
        )
    return row_count


def main() -> None:
    """Point d'entrée principal : construit le résumé des coûts et le classement.

    Returns:
        None
    """
    logger.info("=== Construction résumé coûts + classement → Gold ===")
    n_summary = build_cost_summary()
    n_leaderboard = build_activity_leaderboard()
    logger.info(
        "=== Terminé : %d BU dans gold.cost_summary, %d salariés dans gold.activity_leaderboard ===",
        n_summary,
        n_leaderboard,
    )


if __name__ == "__main__":
    main()
