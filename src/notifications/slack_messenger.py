"""Module de notifications Slack pour les activités sportives du POC."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import requests

from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Données de configuration — emojis, verbes, templates
# ---------------------------------------------------------------------------

_SPORT_EMOJIS: dict[str, str] = {
    "Running": "🏃",
    "Cycling": "🚴",
    "Swimming": "🏊",
    "Tennis": "🎾",
    "Yoga": "🧘",
    "Escalade": "🧗",
    "Football": "⚽",
    "Basketball": "🏀",
    "Pilates": "🤸",
    "Natation": "🏊",
    "Randonnée": "🥾",
    "Badminton": "🏸",
    "Volleyball": "🏐",
    "Boxe": "🥊",
    "Ski": "⛷️",
    "Marche sportive": "🚶",
}
_DEFAULT_EMOJI = "💪"

_SPORT_VERBS: dict[str, str] = {
    "Running": "courir",
    "Cycling": "parcourir à vélo",
    "Natation": "nager",
    "Randonnée": "randonner sur",
    "Marche sportive": "marcher sur",
    "Ski": "skier sur",
    "Swimming": "nager",
}
_DEFAULT_VERB = "parcourir"

_TEMPLATES_WITH_DISTANCE = [
    "Bravo {prenom} {nom} {emoji} ! Tu viens de {verb} {dist} km en {dur} ! {encouragement}",
    "{emoji} Belle sortie {prenom} {nom} ! {dist} km de {sport} en {dur} — {encouragement}",
    "🔥 {prenom} {nom} — {dist} km de {sport} en {dur}. {encouragement}",
    "{emoji} {prenom} {nom} : {dist} km de {sport} en {dur}. {encouragement}",
]

_TEMPLATES_WITHOUT_DISTANCE = [
    "Bravo {prenom} {nom} {emoji} ! Une session de {sport} de {dur}, bien joué ! {encouragement}",
    "{emoji} {prenom} {nom} en mode sport : {dur} de {sport}. {encouragement}",
    "💪 {prenom} {nom} — {dur} de {sport} au compteur. {encouragement}",
    "{emoji} Bel effort {prenom} {nom} ! {dur} de {sport} aujourd'hui. {encouragement}",
]

_ENCOURAGEMENTS = [
    "Quelle énergie !",
    "Impressionnant !",
    "Continue comme ça !",
    "Superbe performance !",
    "Tu assures !",
    "Félicitations !",
    "Excellent effort !",
    "Bravo champion·ne !",
]


# ---------------------------------------------------------------------------
# Fonctions internes
# ---------------------------------------------------------------------------

def _hash_index(key: str, n: int) -> int:
    """Retourne un index stable basé sur le hash MD5 d'une clé.

    Args:
        key: Clé à hasher (nom du salarié pour garantir la variété).
        n: Taille de la liste cible.

    Returns:
        Index entre 0 et n-1, déterministe pour une même clé.
    """
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % n


def _format_duration(temps_ecoule_s: int) -> str:
    """Convertit une durée en secondes en format lisible (Xh Ymin ou Y min).

    Args:
        temps_ecoule_s: Durée en secondes.

    Returns:
        Durée formatée : "45 min" si < 60 min, "1h30min" si >= 60 min.

    Example:
        >>> _format_duration(2700)
        '45 min'
        >>> _format_duration(5400)
        '1h30min'
    """
    minutes_total = temps_ecoule_s // 60
    if minutes_total < 60:
        return f"{minutes_total} min"
    hours = minutes_total // 60
    mins = minutes_total % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h{mins:02d}min"


# ---------------------------------------------------------------------------
# Fonctions publiques
# ---------------------------------------------------------------------------

def format_activity_message(
    prenom: str,
    nom: str,
    sport_type: str,
    distance_m: int | None,
    temps_ecoule_s: int,
    commentaire: str | None,
) -> str:
    """Génère un message Slack motivant pour une activité sportive.

    Le template est choisi de façon déterministe via un hash du nom du salarié,
    garantissant la variété tout en restant reproductible (sans aléatoire à l'exécution).

    Args:
        prenom: Prénom du salarié.
        nom: Nom du salarié.
        sport_type: Type de sport (ex: "Running", "Tennis").
        distance_m: Distance en mètres (None si non applicable, ex: Yoga).
        temps_ecoule_s: Durée de l'activité en secondes.
        commentaire: Commentaire optionnel de l'activité (ajouté entre guillemets).

    Returns:
        Message Slack formaté avec emoji, durée et encouragement.

    Example:
        >>> msg = format_activity_message("Alice", "Dupont", "Running", 10800, 2700, None)
        >>> "10.8" in msg and "Alice" in msg
        True
        >>> msg2 = format_activity_message("Bob", "Martin", "Tennis", None, 5400, "Top !")
        >>> "Tennis" in msg2 and "Top !" in msg2
        True
    """
    emoji = _SPORT_EMOJIS.get(sport_type, _DEFAULT_EMOJI)
    dur = _format_duration(temps_ecoule_s)
    encouragement = _ENCOURAGEMENTS[_hash_index(nom, len(_ENCOURAGEMENTS))]

    if distance_m is not None and distance_m > 0:
        dist = round(distance_m / 1000, 1)
        verb = _SPORT_VERBS.get(sport_type, _DEFAULT_VERB)
        template = _TEMPLATES_WITH_DISTANCE[
            _hash_index(nom, len(_TEMPLATES_WITH_DISTANCE))
        ]
        msg = template.format(
            prenom=prenom,
            nom=nom,
            emoji=emoji,
            verb=verb,
            dist=dist,
            dur=dur,
            sport=sport_type,
            encouragement=encouragement,
        )
    else:
        template = _TEMPLATES_WITHOUT_DISTANCE[
            _hash_index(nom, len(_TEMPLATES_WITHOUT_DISTANCE))
        ]
        msg = template.format(
            prenom=prenom,
            nom=nom,
            emoji=emoji,
            dur=dur,
            sport=sport_type,
            encouragement=encouragement,
        )

    if commentaire and commentaire.strip():
        msg += f' "{commentaire.strip()}"'

    return msg


def send_slack_message(
    message: str,
    webhook_url: str | None = None,
) -> bool:
    """Envoie un message sur Slack via webhook ou logue en mode dry-run.

    Si aucun webhook n'est configuré (paramètre None et variable d'env absente),
    logue le message en WARNING et retourne False sans lever d'exception.

    Args:
        message: Texte du message Slack.
        webhook_url: URL du webhook Slack. Si None, lit SLACK_WEBHOOK_URL depuis .env.

    Returns:
        True si le message a été envoyé avec succès, False en dry-run ou erreur.

    Example:
        >>> send_slack_message("Test", webhook_url=None)
        False
    """
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL", "")

    logger.info("Message Slack : %s", message)

    if not url:
        logger.warning(
            "Mode dry-run : SLACK_WEBHOOK_URL non configuré — message non envoyé"
        )
        return False

    try:
        response = requests.post(
            url,
            json={"text": message},
            timeout=10,
        )
        if response.status_code == 200:
            logger.info("Message Slack envoyé avec succès")
            return True
        logger.error(
            "Échec envoi Slack : HTTP %d — %s", response.status_code, response.text
        )
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("Erreur réseau lors de l'envoi Slack : %s", exc)
        return False


def notify_recent_activities(
    db_path: str = DEFAULT_DB_PATH,
    hours: int = 24,
    webhook_url: str | None = None,
) -> int:
    """Notifie les activités sportives des N dernières heures via Slack.

    Lit silver.strava_activities JOIN silver.employees, filtre sur la fenêtre
    temporelle, formate et envoie (ou logue en dry-run) chaque activité.
    Retourne toujours le nombre d'activités traitées, qu'elles aient été
    effectivement envoyées ou seulement loguées.

    Args:
        db_path: Chemin vers le fichier DuckDB.
        hours: Fenêtre temporelle en heures (défaut: 24).
        webhook_url: URL du webhook Slack (optionnel).

    Returns:
        Nombre de messages traités (loggés ou envoyés).

    Example:
        >>> count = notify_recent_activities(hours=99999, webhook_url=None)
        >>> count >= 0
        True
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    with db_session(db_path) as conn:
        activities = conn.execute(
            """
            SELECT
                sa.id,
                e.prenom,
                e.nom,
                sa.sport_type,
                sa.distance_m,
                sa.temps_ecoule_s,
                sa.commentaire
            FROM silver.strava_activities sa
            JOIN silver.employees e ON sa.id_salarie = e.id_salarie
            WHERE sa.date_debut >= ?
            ORDER BY sa.date_debut DESC
            """,
            [cutoff],
        ).fetchall()

    count = 0
    for row in activities:
        _, prenom, nom, sport_type, distance_m, temps_ecoule_s, commentaire = row
        msg = format_activity_message(
            prenom, nom, sport_type, distance_m, temps_ecoule_s, commentaire
        )
        send_slack_message(msg, webhook_url)
        count += 1

    logger.info(
        "notify_recent_activities : %d message(s) traité(s) (fenêtre %d heures)",
        count,
        hours,
    )
    return count


def notify_single_activity(
    activity_id: int,
    db_path: str = DEFAULT_DB_PATH,
    webhook_url: str | None = None,
) -> bool:
    """Envoie la notification Slack pour une activité spécifique (démo live).

    Args:
        activity_id: Identifiant de l'activité dans silver.strava_activities.
        db_path: Chemin vers le fichier DuckDB.
        webhook_url: URL du webhook Slack (optionnel).

    Returns:
        True si le message a été traité, False si l'activité est introuvable.

    Example:
        >>> notify_single_activity(99999, webhook_url=None)
        False
    """
    with db_session(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                e.prenom,
                e.nom,
                sa.sport_type,
                sa.distance_m,
                sa.temps_ecoule_s,
                sa.commentaire
            FROM silver.strava_activities sa
            JOIN silver.employees e ON sa.id_salarie = e.id_salarie
            WHERE sa.id = ?
            """,
            [activity_id],
        ).fetchone()

    if row is None:
        logger.warning(
            "Activité id=%d introuvable dans silver.strava_activities", activity_id
        )
        return False

    prenom, nom, sport_type, distance_m, temps_ecoule_s, commentaire = row
    msg = format_activity_message(
        prenom, nom, sport_type, distance_m, temps_ecoule_s, commentaire
    )
    send_slack_message(msg, webhook_url)
    return True
