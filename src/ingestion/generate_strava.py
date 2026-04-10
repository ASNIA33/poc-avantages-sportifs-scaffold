"""Génération de données Strava simulées pour la couche Bronze (DuckDB)."""

import random
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

RANDOM_SEED = 42

COMMENTAIRES = [
    "Reprise du sport :)",
    "Super session !",
    "Objectif atteint",
    "Dur mais ça fait du bien",
    "Record personnel !",
    "Belle sortie aujourd'hui",
    "Très satisfait(e) de cette séance",
    "Encore un effort !",
]

# Mapping sport → config d'activité
# distance: (min_m, max_m) ou None si non applicable
# duree_min / duree_max en minutes
SPORT_CONFIG: dict[str, dict] = {
    "Runing": {
        "type": "Course à pied",
        "distance": (3000, 20000),
        "duree_min": 15,
        "duree_max": 120,
    },
    "Running": {
        "type": "Course à pied",
        "distance": (3000, 20000),
        "duree_min": 15,
        "duree_max": 120,
    },
    "Randonnée": {
        "type": "Randonnée",
        "distance": (5000, 25000),
        "duree_min": 60,
        "duree_max": 300,
    },
    "Tennis": {
        "type": "Tennis",
        "distance": None,
        "duree_min": 30,
        "duree_max": 120,
    },
    "Badminton": {
        "type": "Badminton",
        "distance": None,
        "duree_min": 30,
        "duree_max": 120,
    },
    "Tennis de table": {
        "type": "Tennis de table",
        "distance": None,
        "duree_min": 30,
        "duree_max": 120,
    },
    "Football": {
        "type": "Football",
        "distance": None,
        "duree_min": 60,
        "duree_max": 120,
    },
    "Rugby": {
        "type": "Rugby",
        "distance": None,
        "duree_min": 60,
        "duree_max": 120,
    },
    "Basketball": {
        "type": "Basketball",
        "distance": None,
        "duree_min": 60,
        "duree_max": 120,
    },
    "Natation": {
        "type": "Natation",
        "distance": (500, 5000),
        "duree_min": 20,
        "duree_max": 90,
    },
    "Vélo": {
        "type": "Vélo",
        "distance": (10000, 80000),
        "duree_min": 30,
        "duree_max": 240,
    },
    "Triathlon": {
        "type": "Vélo",
        "distance": (10000, 80000),
        "duree_min": 30,
        "duree_max": 240,
    },
    "Escalade": {
        "type": "Escalade",
        "distance": None,
        "duree_min": 60,
        "duree_max": 180,
    },
    "Boxe": {
        "type": "Boxe",
        "distance": None,
        "duree_min": 30,
        "duree_max": 90,
    },
    "Judo": {
        "type": "Judo",
        "distance": None,
        "duree_min": 30,
        "duree_max": 90,
    },
    "Voile": {
        "type": "Voile",
        "distance": None,
        "duree_min": 120,
        "duree_max": 480,
    },
    "Équitation": {
        "type": "Équitation",
        "distance": None,
        "duree_min": 30,
        "duree_max": 120,
    },
}


def generate_strava_data(
    db_path: str = DEFAULT_DB_PATH,
    months: int = 12,
) -> int:
    """Génère des activités sportives simulées pour chaque salarié pratiquant un sport.

    Lit la liste des salariés sportifs depuis bronze.sports_raw (jointure avec
    bronze.rh_raw pour les informations d'identité), génère entre 0 et 40 activités
    aléatoires sur les `months` derniers mois, et insère les résultats dans
    bronze.strava_raw.

    Le générateur est déterministe grâce au seed fixe (RANDOM_SEED = 42).

    Args:
        db_path: Chemin vers le fichier DuckDB cible.
        months: Nombre de mois passés couverts par la simulation (défaut : 12).

    Returns:
        Nombre total de lignes insérées dans bronze.strava_raw.
    """
    random.seed(RANDOM_SEED)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = now - timedelta(days=months * 30)
    date_range_seconds = int((now - start_date).total_seconds())

    logger.info(
        "Génération Strava : période %s → %s",
        start_date.strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d"),
    )

    with db_session(db_path) as conn:
        sportifs = conn.execute(
            """
            SELECT s.id_salarie, r.nom, r.prenom, s.pratique_d_un_sport
            FROM bronze.sports_raw s
            JOIN bronze.rh_raw r ON s.id_salarie = r.id_salarie
            WHERE s.pratique_d_un_sport IS NOT NULL
            ORDER BY s.id_salarie
            """
        ).fetchall()

        logger.info("Salariés sportifs trouvés : %d", len(sportifs))

        activities: list[dict] = []
        activity_id = 1

        for id_salarie, nom, prenom, sport in sportifs:
            config = SPORT_CONFIG.get(sport)
            if config is None:
                logger.warning(
                    "Sport non reconnu : '%s' pour salarié %s — ignoré", sport, id_salarie
                )
                continue

            n_activities = random.randint(0, 40)

            for _ in range(n_activities):
                offset_seconds = random.randint(0, date_range_seconds)
                date_debut = start_date + timedelta(seconds=offset_seconds)

                sport_type: str = config["type"]

                distance_range = config["distance"]
                distance_m: int | None = (
                    random.randint(*distance_range) if distance_range is not None else None
                )

                temps_ecoule_s: int = random.randint(
                    config["duree_min"] * 60,
                    config["duree_max"] * 60,
                )

                commentaire: str | None = (
                    random.choice(COMMENTAIRES) if random.random() < 0.2 else None
                )

                activities.append(
                    {
                        "id": activity_id,
                        "id_salarie": id_salarie,
                        "date_debut": date_debut,
                        "sport_type": sport_type,
                        "distance_m": distance_m,
                        "temps_ecoule_s": temps_ecoule_s,
                        "commentaire": commentaire,
                    }
                )
                activity_id += 1

        if not activities:
            logger.warning("Aucune activité générée — bronze.strava_raw sera vide")
            conn.execute(
                """
                CREATE OR REPLACE TABLE bronze.strava_raw (
                    id INTEGER,
                    id_salarie INTEGER,
                    date_debut TIMESTAMP,
                    sport_type VARCHAR,
                    distance_m INTEGER,
                    temps_ecoule_s INTEGER,
                    commentaire VARCHAR
                )
                """
            )
            return 0

        df = pd.DataFrame(activities)
        conn.execute(
            "CREATE OR REPLACE TABLE bronze.strava_raw AS SELECT * FROM df"
        )

        total = len(activities)
        logger.info("Table bronze.strava_raw créée avec %d activités", total)

    return total


def main() -> None:
    """Point d'entrée principal : génère les données Strava simulées vers Bronze.

    Returns:
        None
    """
    logger.info("=== Démarrage de la simulation Strava → Bronze ===")
    total = generate_strava_data()
    logger.info("=== Simulation terminée : %d activités insérées ===", total)


if __name__ == "__main__":
    main()
