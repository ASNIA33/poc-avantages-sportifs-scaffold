"""Orchestration des transformations Bronze → Silver.

Ce module expose run_all_transformations() qui exécute dans l'ordre :
1. clean_rh_to_silver           → silver.employees
2. clean_sports_to_silver       → silver.sports_activities
3. validate_distances_to_silver → silver.distances
4. clean_strava_to_silver       → silver.strava_activities
"""

from src.transformation.clean_rh import clean_rh_to_silver
from src.transformation.clean_sports import clean_sports_to_silver
from src.transformation.clean_strava import clean_strava_to_silver
from src.transformation.validate_distances import validate_distances_to_silver
from src.utils.db import DEFAULT_DB_PATH
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_all_transformations(db_path: str = DEFAULT_DB_PATH) -> dict[str, int]:
    """Exécute toutes les transformations Bronze → Silver dans l'ordre requis.

    L'ordre est impératif : validate_distances_to_silver dépend de silver.employees
    (produit par clean_rh_to_silver).

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Dictionnaire {nom_table_silver: nombre_de_lignes} pour chaque table créée.

    Example:
        >>> results = run_all_transformations()
        >>> results["employees"]
        161
    """
    logger.info("=== Démarrage des transformations Bronze → Silver ===")

    results: dict[str, int] = {}

    results["employees"] = clean_rh_to_silver(db_path)
    results["sports_activities"] = clean_sports_to_silver(db_path)
    results["distances"] = validate_distances_to_silver(db_path)
    results["strava_activities"] = clean_strava_to_silver(db_path)

    logger.info(
        "=== Transformations terminées — employees=%d | sports=%d | distances=%d | strava=%d ===",
        results["employees"],
        results["sports_activities"],
        results["distances"],
        results["strava_activities"],
    )
    return results
