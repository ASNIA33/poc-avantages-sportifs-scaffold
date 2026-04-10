"""Calcul des distances domicile-bureau pour les salariés sportifs → Bronze (DuckDB).

Deux modes de fonctionnement :
- Mode API réelle  : si GOOGLE_MAPS_API_KEY est défini, utilise Google Maps Distance Matrix
- Mode simulation  : fallback haversine avec coordonnées GPS des villes de la région

Le mode simulation est suffisant pour faire tourner le pipeline sans clé API.
"""

import math
import re

import pandas as pd
import requests

from src.utils.config import COMPANY_ADDRESS, GOOGLE_MAPS_API_KEY
from src.utils.db import DEFAULT_DB_PATH, db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Coordonnées GPS de l'entreprise (1362 Av. des Platanes, 34970 Lattes)
_COMPANY_LAT: float = 43.5700
_COMPANY_LON: float = 3.9000

# Mapping moyen_de_deplacement → mode Google Maps
_MODE_MAP: dict[str, str] = {
    "Marche/running": "walking",
    "Vélo/Trottinette/Autres": "bicycling",
}

# Coordonnées GPS des villes de la région Montpellier / Hérault / Gard
# Note : les coordonnées représentent le centre-ville, distinct de l'adresse exacte
# de l'entreprise (→ distance non nulle même pour les résidents de Lattes)
_CITY_GPS: dict[str, tuple[float, float]] = {
    "Lattes": (43.5670, 3.8938),  # centre-ville de Lattes (mairie)
    "Montpellier": (43.6108, 3.8767),
    "Pérols": (43.5617, 3.9208),
    "Mauguio": (43.6178, 4.0069),
    "Castelnau-le-Lez": (43.6322, 3.9083),
    "Palavas-les-Flots": (43.5289, 3.9289),
    "La Grande-Motte": (43.5589, 4.0847),
    "Fabrègues": (43.5533, 3.7711),
    "Villeneuve-lès-Maguelone": (43.5119, 3.8578),
    "Clapiers": (43.6531, 3.8806),
    "Le Crès": (43.6406, 3.9314),
    "Saint-Clément-de-Rivière": (43.6878, 3.8578),
    "Valergues": (43.6453, 4.0406),
    "Frontignan": (43.4478, 3.7539),
    "Mèze": (43.4256, 3.6086),
    "Prades-le-Lez": (43.7000, 3.8500),
    "Nîmes": (43.8367, 4.3600),
    "Aigues-Mortes": (43.5656, 4.1928),
    "Jacou": (43.6656, 3.9350),
    "Grabels": (43.6331, 3.8289),
    "Juvignac": (43.6119, 3.8183),
    "Baillargues": (43.6514, 3.9981),
    "Sète": (43.4053, 3.6956),
    "Lunel": (43.6750, 4.1369),
}

_DEFAULT_DISTANCE_KM: float = 15.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance en km entre deux points GPS via la formule haversine.

    Args:
        lat1: Latitude du point de départ (degrés décimaux).
        lon1: Longitude du point de départ (degrés décimaux).
        lat2: Latitude du point d'arrivée (degrés décimaux).
        lon2: Longitude du point d'arrivée (degrés décimaux).

    Returns:
        Distance à vol d'oiseau en kilomètres.
    """
    R = 6371.0  # rayon terrestre moyen en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _extract_city(address: str) -> str:
    """Extrait le nom de la ville depuis une adresse postale française.

    Cherche en priorité un code postal à 5 chiffres suivi du nom de ville.
    En l'absence de code postal, prend la dernière partie après la dernière virgule.

    Args:
        address: Adresse postale complète (ex : "53 Av. de la Gare, 34970 Lattes").

    Returns:
        Nom de la ville extrait (ex : "Lattes").
    """
    match = re.search(r"\b\d{5}\s+(.+?)(?:\s*,|$)", address.strip())
    if match:
        return match.group(1).strip()
    parts = address.split(",")
    return parts[-1].strip()


def _calculate_distance_haversine(address: str) -> float:
    """Calcule la distance domicile-entreprise par approximation haversine.

    Extrait la ville depuis l'adresse, la recherche dans le dictionnaire GPS
    local, puis calcule la distance haversine vers le siège à Lattes.
    Si la ville est inconnue, retourne la distance par défaut (15 km) et log un WARNING.

    Args:
        address: Adresse domicile du salarié.

    Returns:
        Distance estimée en km (arrondie à 2 décimales).
    """
    city = _extract_city(address)
    coords = _CITY_GPS.get(city)

    if coords is None:
        logger.warning(
            "Ville '%s' absente du dictionnaire GPS — distance par défaut %.1f km utilisée",
            city,
            _DEFAULT_DISTANCE_KM,
        )
        return _DEFAULT_DISTANCE_KM

    distance_km = _haversine_km(coords[0], coords[1], _COMPANY_LAT, _COMPANY_LON)
    logger.info("Haversine — %s : %.2f km", city, distance_km)
    return round(distance_km, 2)


def _calculate_distance_api(address: str, mode: str, api_key: str) -> float:
    """Calcule la distance domicile-entreprise via Google Maps Distance Matrix API.

    Args:
        address: Adresse domicile du salarié.
        mode: Mode de déplacement ('walking' ou 'bicycling').
        api_key: Clé API Google Maps.

    Returns:
        Distance en km selon l'itinéraire réel (arrondie à 2 décimales).

    Raises:
        ValueError: Si l'API retourne un statut inattendu ou une erreur.
        requests.RequestException: En cas d'erreur réseau.
    """
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": address,
        "destinations": COMPANY_ADDRESS,
        "mode": mode,
        "language": "fr",
        "key": api_key,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "OK":
        raise ValueError(f"Google Maps API statut inattendu : {data.get('status')}")

    element = data["rows"][0]["elements"][0]
    if element.get("status") != "OK":
        raise ValueError(f"Élément de distance en erreur : {element.get('status')}")

    distance_m = element["distance"]["value"]
    return round(distance_m / 1000, 2)


def fetch_distances_to_bronze(
    db_path: str = DEFAULT_DB_PATH,
    api_key: str | None = None,
) -> int:
    """Calcule les distances domicile-bureau des salariés sportifs et insère dans Bronze.

    Lit les salariés avec moyen_de_deplacement IN ('Marche/running', 'Vélo/Trottinette/Autres')
    depuis bronze.rh_raw. Pour chaque salarié, calcule la distance via l'API Google Maps
    (si api_key fournie ou GOOGLE_MAPS_API_KEY défini) ou via haversine (mode simulation).

    En cas d'erreur API pour un salarié, le fallback haversine est automatiquement utilisé.

    Args:
        db_path: Chemin vers le fichier DuckDB cible.
        api_key: Clé API Google Maps à utiliser. Si None, lit GOOGLE_MAPS_API_KEY depuis
            la configuration. Passer "" pour forcer le mode simulation.

    Returns:
        Nombre de lignes insérées dans bronze.distances_raw.
    """
    effective_key = api_key if api_key is not None else GOOGLE_MAPS_API_KEY
    use_api = bool(effective_key)
    source_label = "api" if use_api else "simulation"

    logger.info(
        "Calcul des distances — mode : %s | entreprise : %s",
        source_label.upper(),
        COMPANY_ADDRESS,
    )

    with db_session(db_path) as conn:
        sportifs = conn.execute(
            """
            SELECT id_salarie, adresse_du_domicile, moyen_de_deplacement
            FROM bronze.rh_raw
            WHERE moyen_de_deplacement IN ('Marche/running', 'Vélo/Trottinette/Autres')
            ORDER BY id_salarie
            """
        ).fetchall()

        logger.info("Salariés sportifs à traiter : %d", len(sportifs))

        records: list[dict] = []
        for id_salarie, adresse, moyen in sportifs:
            mode_transport = _MODE_MAP.get(str(moyen), "walking")
            adresse_str = str(adresse) if adresse else ""

            try:
                if use_api:
                    distance_km = _calculate_distance_api(
                        adresse_str, mode_transport, effective_key
                    )
                else:
                    distance_km = _calculate_distance_haversine(adresse_str)
            except Exception as exc:
                logger.warning(
                    "Erreur calcul distance pour %s (%s) — fallback haversine : %s",
                    id_salarie,
                    adresse_str,
                    exc,
                )
                distance_km = _calculate_distance_haversine(adresse_str)

            logger.info(
                "Salarié %s | %s | %.2f km | source : %s",
                id_salarie,
                mode_transport,
                distance_km,
                source_label,
            )
            records.append(
                {
                    "id_salarie": id_salarie,
                    "adresse_domicile": adresse_str,
                    "distance_km": distance_km,
                    "mode_transport": mode_transport,
                    "source": source_label,
                }
            )

        if not records:
            logger.warning("Aucun salarié sportif trouvé — bronze.distances_raw sera vide")
            conn.execute(
                """
                CREATE OR REPLACE TABLE bronze.distances_raw (
                    id_salarie INTEGER,
                    adresse_domicile VARCHAR,
                    distance_km DOUBLE,
                    mode_transport VARCHAR,
                    source VARCHAR
                )
                """
            )
            return 0

        df = pd.DataFrame(records)
        conn.execute("CREATE OR REPLACE TABLE bronze.distances_raw AS SELECT * FROM df")
        total = len(records)
        logger.info("Table bronze.distances_raw créée avec %d lignes", total)

    return total


def main() -> None:
    """Point d'entrée principal : calcule les distances domicile-bureau → Bronze.

    Returns:
        None
    """
    logger.info("=== Démarrage du calcul des distances domicile-bureau ===")
    total = fetch_distances_to_bronze()
    logger.info("=== Calcul terminé : %d distances insérées ===", total)


if __name__ == "__main__":
    main()
