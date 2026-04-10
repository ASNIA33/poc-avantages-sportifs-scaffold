"""Configuration centralisée pour le pipeline POC Avantages Sportifs.

Charge les variables depuis .env (python-dotenv) et expose des constantes
avec leurs valeurs par défaut. Ces paramètres sont les variables dynamiques
du projet, configurables sans modifier le code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Charge .env depuis la racine du projet (s'il existe)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path, override=False)

# Paramètres métier
COMPANY_ADDRESS: str = os.getenv(
    "COMPANY_ADDRESS", "1362 Avenue des Platanes, 34970 Lattes"
)
WALK_MAX_KM: float = float(os.getenv("WALK_MAX_DISTANCE_KM", "15"))
BIKE_MAX_KM: float = float(os.getenv("BIKE_MAX_DISTANCE_KM", "25"))
PRIME_RATE: float = float(os.getenv("PRIME_RATE", "0.05"))
WELLBEING_THRESHOLD: int = int(os.getenv("WELLBEING_THRESHOLD", "15"))

# Clé API Google Maps (vide → mode simulation haversine)
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")


def get_config() -> dict:
    """Retourne tous les paramètres de configuration du pipeline.

    Returns:
        Dictionnaire des paramètres avec leurs valeurs actuelles.
        La clé API n'est pas exposée — seule sa présence est indiquée.

    Example:
        >>> cfg = get_config()
        >>> cfg["prime_rate"]
        0.05
    """
    return {
        "company_address": COMPANY_ADDRESS,
        "walk_max_km": WALK_MAX_KM,
        "bike_max_km": BIKE_MAX_KM,
        "prime_rate": PRIME_RATE,
        "wellbeing_threshold": WELLBEING_THRESHOLD,
        "google_maps_api_key_set": bool(GOOGLE_MAPS_API_KEY),
    }
