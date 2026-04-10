"""Ingestion des fichiers Excel RH et Sportif vers la couche Bronze (DuckDB)."""

import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Racine du projet : 3 niveaux au-dessus de src/ingestion/load_excel.py
# En local  : calculé depuis __file__ (fonctionne quel que soit le CWD)
# En Docker : PROJECT_ROOT=/app injecté via ENV dans Dockerfile.kestra
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent.parent)))
RH_FILE = PROJECT_ROOT / "input" / "Donnees_RH.xlsx"
SPORTS_FILE = PROJECT_ROOT / "input" / "Donnees_Sportive.xlsx"


def _normalize_column_name(name: str) -> str:
    """Normalise un nom de colonne en snake_case sans accents.

    Args:
        name: Nom de colonne brut.

    Returns:
        Nom normalisé : minuscules, sans accents, espaces remplacés par _.
    """
    nfd = unicodedata.normalize("NFD", name)
    ascii_name = nfd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_name.lower()
    snake = re.sub(r"[^a-z0-9]+", "_", lower)
    return snake.strip("_")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renomme toutes les colonnes d'un DataFrame en snake_case.

    Args:
        df: DataFrame dont les colonnes doivent être normalisées.

    Returns:
        DataFrame avec colonnes renommées.
    """
    df.columns = [_normalize_column_name(col) for col in df.columns]
    return df


def load_rh_to_bronze(db_path: str = DEFAULT_DB_PATH) -> int:
    """Charge le fichier Excel RH dans la table bronze.rh_raw.

    Lit input/Donnees_RH.xlsx, normalise les noms de colonnes en snake_case,
    ajoute un timestamp d'ingestion UTC, puis insère les données dans DuckDB.

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans bronze.rh_raw.
    """
    logger.info("Lecture du fichier RH : %s", RH_FILE)
    df = pd.read_excel(RH_FILE)

    df = _normalize_columns(df)
    df["_ingested_at"] = datetime.now(timezone.utc)

    row_count = len(df)
    logger.info("Lignes lues depuis %s : %d", RH_FILE, row_count)

    with db_session(db_path) as conn:
        conn.execute("CREATE OR REPLACE TABLE bronze.rh_raw AS SELECT * FROM df")
        logger.info("Table bronze.rh_raw créée avec %d lignes", row_count)

    return row_count


def load_sports_to_bronze(db_path: str = DEFAULT_DB_PATH) -> int:
    """Charge le fichier Excel Sportif dans la table bronze.sports_raw.

    Lit input/Donnees_Sportive.xlsx, normalise les noms de colonnes en snake_case,
    ajoute un timestamp d'ingestion UTC, puis insère les données dans DuckDB.

    Args:
        db_path: Chemin vers le fichier DuckDB cible.

    Returns:
        Nombre de lignes insérées dans bronze.sports_raw.
    """
    logger.info("Lecture du fichier Sportif : %s", SPORTS_FILE)
    df = pd.read_excel(SPORTS_FILE)

    df = _normalize_columns(df)
    df["_ingested_at"] = datetime.now(timezone.utc)

    row_count = len(df)
    logger.info("Lignes lues depuis %s : %d", SPORTS_FILE, row_count)

    with db_session(db_path) as conn:
        conn.execute("CREATE OR REPLACE TABLE bronze.sports_raw AS SELECT * FROM df")
        logger.info("Table bronze.sports_raw créée avec %d lignes", row_count)

    return row_count


def main() -> None:
    """Point d'entrée principal : charge RH et Sportif en Bronze.

    Returns:
        None
    """
    logger.info("=== Démarrage de l'ingestion Excel → Bronze ===")

    rh_count = load_rh_to_bronze()
    logger.info("RH ingéré : %d lignes", rh_count)

    sports_count = load_sports_to_bronze()
    logger.info("Sportif ingéré : %d lignes", sports_count)

    logger.info("=== Ingestion terminée (RH: %d, Sports: %d) ===", rh_count, sports_count)


if __name__ == "__main__":
    main()
