#!/usr/bin/env python3
"""Point d'entrée CLI pour le pipeline POC Avantages Sportifs.

Permet d'exécuter le pipeline complet (Bronze → Silver → Gold) ou des étapes
individuelles sans passer par Kestra. Utile pour le développement et la démo.

Utilisation :
    python main.py run                    # Pipeline complet
    python main.py run --notify           # Pipeline complet + notifications Slack
    python main.py notify                 # Notifications des 24 dernières heures
    python main.py notify --id 42         # Notification pour une activité spécifique
    python main.py status                 # Nombre de lignes par table DuckDB

Options globales :
    --prime-rate 0.08    Override le taux de prime (défaut : 0.05)
    --threshold 10       Override le seuil bien-être (défaut : 15)
    --db-path chemin     Override le chemin DuckDB
"""

import argparse
import sys

from src.ingestion.fetch_distances import fetch_distances_to_bronze
from src.ingestion.generate_strava import generate_strava_data
from src.ingestion.load_excel import load_rh_to_bronze, load_sports_to_bronze
from src.business import run_all_business
from src.notifications.slack_messenger import (
    notify_recent_activities,
    notify_single_activity,
)
from src.transformation import run_all_transformations
from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger("main")

# Tables par couche — pour la commande status
_PIPELINE_TABLES: dict[str, list[tuple[str, str]]] = {
    "Bronze": [
        ("bronze", "rh_raw"),
        ("bronze", "sports_raw"),
        ("bronze", "distances_raw"),
        ("bronze", "strava_raw"),
    ],
    "Silver": [
        ("silver", "employees"),
        ("silver", "sports_activities"),
        ("silver", "distances"),
        ("silver", "strava_activities"),
    ],
    "Gold": [
        ("gold", "prime_eligibility"),
        ("gold", "wellbeing_eligibility"),
        ("gold", "distance_anomalies"),
        ("gold", "cost_summary"),
        ("gold", "activity_leaderboard"),
    ],
}


# ---------------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    """Exécute le pipeline complet Bronze → Silver → Gold.

    Args:
        args: Arguments parsés par argparse.
    """
    db_path: str = args.db_path

    logger.info("=== Pipeline — Couche Bronze (Ingestion) ===")
    load_rh_to_bronze(db_path)
    load_sports_to_bronze(db_path)
    fetch_distances_to_bronze(db_path)
    generate_strava_data(db_path)

    logger.info("=== Pipeline — Couche Silver (Transformation) ===")
    run_all_transformations(db_path)

    logger.info("=== Pipeline — Couche Gold (Calculs métier) ===")
    gold_results = run_all_business(
        db_path,
        prime_rate=args.prime_rate,
        threshold=args.threshold,
    )

    if args.notify:
        logger.info("=== Pipeline — Notifications Slack ===")
        n_notif = notify_recent_activities(db_path, hours=24)
        logger.info("%d message(s) Slack traité(s)", n_notif)

    _print_summary(db_path, gold_results)


def cmd_notify(args: argparse.Namespace) -> None:
    """Envoie les notifications Slack (activités récentes ou activité spécifique).

    Args:
        args: Arguments parsés par argparse.
    """
    db_path: str = args.db_path

    if args.id is not None:
        logger.info("Notification pour l'activité id=%d", args.id)
        sent = notify_single_activity(args.id, db_path)
        if not sent:
            logger.warning("Activité id=%d introuvable", args.id)
            sys.exit(1)
    else:
        logger.info("Notifications — activités des 24 dernières heures")
        count = notify_recent_activities(db_path, hours=24)
        logger.info("%d message(s) traité(s)", count)


def cmd_status(args: argparse.Namespace) -> None:
    """Affiche le nombre de lignes par table DuckDB (état du pipeline).

    Args:
        args: Arguments parsés par argparse.
    """
    db_path: str = args.db_path
    logger.info("Statut du pipeline — %s", db_path)

    try:
        with db_session(db_path) as conn:
            for layer, tables in _PIPELINE_TABLES.items():
                print(f"\n{'─' * 48}")
                print(f"  {layer}")
                print(f"{'─' * 48}")
                for schema, table in tables:
                    try:
                        count = conn.execute(
                            f"SELECT COUNT(*) FROM {schema}.{table}"
                        ).fetchone()[0]
                        print(f"  {schema}.{table:<35} {count:>6} lignes")
                    except Exception:
                        print(f"  {schema}.{table:<35}  (table absente)")
    except Exception as exc:
        logger.error("Impossible de lire la base DuckDB : %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Résumé final
# ---------------------------------------------------------------------------

def _print_summary(db_path: str, gold_results: dict[str, int]) -> None:
    """Affiche un résumé final du pipeline avec les KPI Gold.

    Args:
        db_path: Chemin vers le fichier DuckDB.
        gold_results: Dictionnaire {nom_table: nb_lignes} retourné par run_all_business.
            Utilisé pour afficher le nombre de salariés classés dans le leaderboard.
    """
    n_leaderboard = gold_results.get("activity_leaderboard", 0)
    try:
        with db_session(db_path) as conn:
            total_cost = conn.execute(
                "SELECT COALESCE(SUM(prime_montant), 0) FROM gold.prime_eligibility"
            ).fetchone()[0]
            n_prime = conn.execute(
                "SELECT COUNT(*) FROM gold.prime_eligibility WHERE is_eligible = TRUE"
            ).fetchone()[0]
            n_wellbeing = conn.execute(
                "SELECT COUNT(*) FROM gold.wellbeing_eligibility WHERE is_eligible = TRUE"
            ).fetchone()[0]
            n_anomalies = conn.execute(
                "SELECT COUNT(*) FROM gold.distance_anomalies"
            ).fetchone()[0]
    except Exception as exc:
        logger.warning("Résumé partiel — tables Gold incomplètes : %s", exc)
        return

    print("\n" + "=" * 55)
    print("  RÉSUMÉ PIPELINE — POC Avantages Sportifs")
    print("=" * 55)
    print(f"  Prime sportive    : {n_prime:>4} éligibles | Coût total : {total_cost:>12,.2f} €")
    print(f"  Jours bien-être   : {n_wellbeing:>4} éligibles | 5 jours/an")
    print(f"  Anomalies distance: {n_anomalies:>4} détectée(s)")
    print(f"  Classement activités: {n_leaderboard} salariés classés")
    print("=" * 55)


# ---------------------------------------------------------------------------
# Point d'entrée — parsing argparse
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Construit le parser argparse avec toutes les sous-commandes.

    Returns:
        Parser argparse configuré.
    """
    parser = argparse.ArgumentParser(
        description="POC Avantages Sportifs — Pipeline CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Options globales communes à toutes les sous-commandes
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        metavar="CHEMIN",
        help=f"Chemin vers le fichier DuckDB (défaut : {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--prime-rate",
        type=float,
        default=None,
        metavar="TAUX",
        help="Override le taux de prime (ex : 0.08 pour 8%%, défaut : 0.05)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        metavar="SEUIL",
        help="Override le seuil d'activités pour les jours bien-être (défaut : 15)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMANDE")
    subparsers.required = True

    # --- Sous-commande : run ---
    run_parser = subparsers.add_parser(
        "run",
        help="Exécute le pipeline complet Bronze → Silver → Gold",
        description="Charge, transforme et calcule tous les KPI depuis les sources.",
    )
    run_parser.add_argument(
        "--notify",
        action="store_true",
        help="Envoie les notifications Slack après le pipeline Gold",
    )
    run_parser.set_defaults(func=cmd_run)

    # --- Sous-commande : notify ---
    notify_parser = subparsers.add_parser(
        "notify",
        help="Envoie les notifications Slack (Silver requis en base)",
        description="Envoie les messages Slack pour les activités récentes.",
    )
    notify_parser.add_argument(
        "--id",
        type=int,
        default=None,
        metavar="ID",
        help="ID d'une activité spécifique (silver.strava_activities.id)",
    )
    notify_parser.set_defaults(func=cmd_notify)

    # --- Sous-commande : status ---
    status_parser = subparsers.add_parser(
        "status",
        help="Affiche le nombre de lignes par table DuckDB",
        description="Montre l'état du pipeline couche par couche.",
    )
    status_parser.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    """Point d'entrée principal du CLI.

    Returns:
        None
    """
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
