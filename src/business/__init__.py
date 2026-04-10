"""Orchestration des calculs métier Silver → Gold.

Ce module expose run_all_business() qui exécute dans l'ordre :
1. compute_prime_eligibility    → gold.prime_eligibility
2. compute_wellbeing_eligibility → gold.wellbeing_eligibility
3. detect_distance_anomalies    → gold.distance_anomalies
4. build_cost_summary           → gold.cost_summary
5. build_activity_leaderboard   → gold.activity_leaderboard
"""

from src.business.build_summary import build_activity_leaderboard, build_cost_summary
from src.business.compute_prime import compute_prime_eligibility
from src.business.compute_wellbeing import compute_wellbeing_eligibility
from src.business.detect_anomalies import detect_distance_anomalies
from src.utils.db import DEFAULT_DB_PATH
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_all_business(
    db_path: str = DEFAULT_DB_PATH,
    prime_rate: float | None = None,
    threshold: int | None = None,
) -> dict[str, int]:
    """Exécute tous les calculs métier Silver → Gold dans l'ordre requis.

    L'ordre est impératif :
    - prime et wellbeing doivent précéder cost_summary (qui les agrège)
    - detect_anomalies est indépendant mais logiquement lié à prime

    Args:
        db_path: Chemin vers le fichier DuckDB cible.
        prime_rate: Taux de la prime (ex: 0.05). Utilise config si None.
        threshold: Seuil d'activités pour les jours bien-être. Utilise config si None.

    Returns:
        Dictionnaire {nom_table_gold: nombre_de_lignes} pour chaque table créée.

    Example:
        >>> results = run_all_business()
        >>> results["prime_eligibility"]
        68
    """
    logger.info("=== Démarrage des calculs métier Silver → Gold ===")

    results: dict[str, int] = {}

    results["prime_eligibility"] = compute_prime_eligibility(db_path, prime_rate)
    results["wellbeing_eligibility"] = compute_wellbeing_eligibility(db_path, threshold)
    results["distance_anomalies"] = detect_distance_anomalies(db_path)
    results["cost_summary"] = build_cost_summary(db_path)
    results["activity_leaderboard"] = build_activity_leaderboard(db_path)

    logger.info(
        "=== Calculs métier terminés — prime=%d | wellbeing=%d | anomalies=%d | summary=%d | leaderboard=%d ===",
        results["prime_eligibility"],
        results["wellbeing_eligibility"],
        results["distance_anomalies"],
        results["cost_summary"],
        results["activity_leaderboard"],
    )
    return results
