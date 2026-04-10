"""Tests unitaires pour les notifications Slack — formatage et envoi."""

import os

import duckdb
import pytest

from src.ingestion.fetch_distances import fetch_distances_to_bronze
from src.ingestion.generate_strava import generate_strava_data
from src.ingestion.load_excel import load_rh_to_bronze, load_sports_to_bronze
from src.notifications.slack_messenger import (
    format_activity_message,
    notify_recent_activities,
    send_slack_message,
)
from src.transformation.clean_rh import clean_rh_to_silver
from src.transformation.clean_sports import clean_sports_to_silver
from src.transformation.clean_strava import clean_strava_to_silver
from src.transformation.validate_distances import validate_distances_to_silver

TEST_DB = "/tmp/test_notifications.duckdb"

# Fenêtre large pour capturer toutes les activités simulées (12 mois + marge)
_HOURS_ALL = 24 * 366 + 24


# ---------------------------------------------------------------------------
# Fixture module-scoped : Bronze + Silver prêts pour les tests notify
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def notifications_db():
    """Charge Bronze + Silver en base de test pour les tests de notification.

    Portée module : la DB est créée une seule fois pour tous les tests.
    Les activités Strava simulées couvrent les 12 derniers mois.
    """
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    load_rh_to_bronze(TEST_DB)
    load_sports_to_bronze(TEST_DB)
    fetch_distances_to_bronze(TEST_DB, api_key="")
    generate_strava_data(TEST_DB)
    clean_rh_to_silver(TEST_DB)
    clean_sports_to_silver(TEST_DB)
    validate_distances_to_silver(TEST_DB)
    clean_strava_to_silver(TEST_DB)

    yield

    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _count(sql: str) -> int:
    """Exécute une requête COUNT sur la DB de test.

    Args:
        sql: Requête SQL retournant un entier (COUNT).

    Returns:
        Valeur entière du premier résultat.
    """
    conn = duckdb.connect(TEST_DB)
    result = conn.execute(sql).fetchone()[0]
    conn.close()
    return result


# ---------------------------------------------------------------------------
# Tests format_activity_message — unités pures, pas de DB
# ---------------------------------------------------------------------------

@pytest.mark.notifications
def test_format_message_with_distance() -> None:
    """Le message avec distance doit contenir la distance en km et la durée.

    10 800 m = 10.8 km, 2 700 s = 45 min.
    """
    msg = format_activity_message(
        prenom="Alice",
        nom="Dupont",
        sport_type="Running",
        distance_m=10800,
        temps_ecoule_s=2700,
        commentaire=None,
    )
    assert "10.8" in msg, f"Distance 10.8 km absente du message : {msg!r}"
    assert "Alice" in msg, f"Prénom Alice absent du message : {msg!r}"
    assert "45 min" in msg, f"Durée '45 min' absente du message : {msg!r}"


@pytest.mark.notifications
def test_format_message_without_distance() -> None:
    """Le message sans distance doit contenir le sport et la durée.

    Tennis n'a pas de distance GPS — distance_m = None.
    5 400 s = 1h30min.
    """
    msg = format_activity_message(
        prenom="Bob",
        nom="Martin",
        sport_type="Tennis",
        distance_m=None,
        temps_ecoule_s=5400,
        commentaire=None,
    )
    assert "Tennis" in msg, f"Sport 'Tennis' absent du message : {msg!r}"
    assert "Bob" in msg, f"Prénom Bob absent du message : {msg!r}"
    assert "1h" in msg, f"Durée '1h...' absente du message : {msg!r}"


@pytest.mark.notifications
def test_format_message_with_comment() -> None:
    """Le commentaire doit apparaître entre guillemets à la fin du message."""
    commentaire = "Super séance avec les collègues !"
    msg = format_activity_message(
        prenom="Claire",
        nom="Petit",
        sport_type="Yoga",
        distance_m=None,
        temps_ecoule_s=3600,
        commentaire=commentaire,
    )
    assert commentaire in msg, (
        f"Commentaire '{commentaire}' absent du message : {msg!r}"
    )
    # Le commentaire doit être entre guillemets
    assert f'"{commentaire}"' in msg, (
        f"Commentaire non encadré de guillemets dans : {msg!r}"
    )


@pytest.mark.notifications
def test_format_duration_minutes() -> None:
    """Une durée < 60 min doit s'afficher en 'X min'."""
    msg = format_activity_message(
        prenom="Test",
        nom="User",
        sport_type="Running",
        distance_m=5000,
        temps_ecoule_s=1800,  # 30 min exactement
        commentaire=None,
    )
    assert "30 min" in msg, (
        f"Durée '30 min' absente (1800 s = 30 min) : {msg!r}"
    )


@pytest.mark.notifications
def test_format_duration_hours() -> None:
    """Une durée >= 60 min doit s'afficher en format 'Xh...'."""
    msg = format_activity_message(
        prenom="Test",
        nom="User",
        sport_type="Cycling",
        distance_m=30000,
        temps_ecoule_s=5400,  # 1h30min
        commentaire=None,
    )
    assert "1h" in msg, (
        f"Durée '1h...' absente (5400 s = 1h30min) : {msg!r}"
    )


# ---------------------------------------------------------------------------
# Tests send_slack_message — mode dry-run
# ---------------------------------------------------------------------------

@pytest.mark.notifications
def test_send_dry_run() -> None:
    """Sans webhook configuré, send_slack_message doit retourner False sans exception."""
    result = send_slack_message("Message de test", webhook_url=None)
    assert result is False, (
        f"Mode dry-run attendu (return False), obtenu {result!r}"
    )


# ---------------------------------------------------------------------------
# Tests notify_recent_activities — intégration avec DB
# ---------------------------------------------------------------------------

@pytest.mark.notifications
def test_notify_recent_count() -> None:
    """notify_recent_activities doit retourner autant de messages que d'activités en DB.

    Utilise une fenêtre de 366 jours + marge pour capturer toutes les activités
    simulées (générées sur les 12 derniers mois).
    """
    expected = _count("SELECT COUNT(*) FROM silver.strava_activities")
    count = notify_recent_activities(TEST_DB, hours=_HOURS_ALL, webhook_url=None)
    assert count == expected, (
        f"Attendu {expected} messages (toutes activités), obtenu {count}"
    )
