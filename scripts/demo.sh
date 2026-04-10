#!/usr/bin/env bash
# =============================================================================
# scripts/demo.sh — Démonstration live du pipeline POC Avantages Sportifs
#
# Simule l'arrivée d'une nouvelle activité Strava (Running 12 km, 55 min),
# recalcule les KPI Gold, envoie la notification Slack, et affiche le résultat.
#
# Pré-requis :
#   - Infrastructure démarrée (./scripts/start.sh)
#   - Environnement Python actif (.venv ou python3)
#
# Usage :
#   chmod +x scripts/demo.sh
#   ./scripts/demo.sh
#   ./scripts/demo.sh --id 999   # notification pour l'activité insérée
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${CYAN}[demo.sh]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
step() { echo -e "\n${BOLD}$*${NC}"; }

# Résolution du binaire Python
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

DB_PATH="${DUCKDB_PATH:-data/sports_poc.duckdb}"

# ---------------------------------------------------------------------------
# Étape 1 : Injection d'une activité Running fictive
# ---------------------------------------------------------------------------
step "1/4 — Injection d'une activité Running (12 km, 55 min) dans Bronze..."

"$PYTHON" - <<'PYTHON'
import duckdb
import os
from datetime import datetime, timezone

db_path = os.getenv("DUCKDB_PATH", "data/sports_poc.duckdb")
conn = duckdb.connect(db_path)

# Récupérer un salarié Marche/running existant comme cobaye de démo
row = conn.execute("""
    SELECT e.id_salarie, e.prenom, e.nom
    FROM silver.employees e
    JOIN silver.distances d ON d.id_salarie = e.id_salarie
    WHERE e.moyen_deplacement = 'Marche/running'
    LIMIT 1
""").fetchone()

if row is None:
    print("Aucun salarié Marche/running trouvé — démo annulée.")
    conn.close()
    exit(1)

id_salarie, prenom, nom = row
now = datetime.now(timezone.utc).replace(tzinfo=None)

# Insérer dans strava_raw
conn.execute("""
    INSERT INTO bronze.strava_raw
        (id_salarie, sport_type, distance_m, temps_ecoule_s, date_debut, commentaire, _ingested_at)
    VALUES (?, 'Run', 12000, 3300, ?, 'Super sortie matinale !', ?)
""", [id_salarie, now, now])

# Récupérer l'ID inséré (max id dans strava_raw)
new_id = conn.execute("SELECT MAX(rowid) FROM bronze.strava_raw").fetchone()[0]
print(f"Activité insérée pour {prenom} {nom} (id_salarie={id_salarie})")
conn.close()
PYTHON

ok "Activité injectée dans bronze.strava_raw."

# ---------------------------------------------------------------------------
# Étape 2 : Recalcul Silver (strava uniquement) + Gold complet
# ---------------------------------------------------------------------------
step "2/4 — Recalcul de la couche Silver (Strava) et Gold..."

"$PYTHON" - <<'PYTHON'
import os, sys
sys.path.insert(0, ".")
db_path = os.getenv("DUCKDB_PATH", "data/sports_poc.duckdb")

from src.transformation.clean_strava import clean_strava_to_silver
from src.business import run_all_business

clean_strava_to_silver(db_path)
run_all_business(db_path)
print("Recalcul Silver + Gold terminé.")
PYTHON

ok "KPI Gold recalculés."

# ---------------------------------------------------------------------------
# Étape 3 : Notification Slack (dry-run ou réelle selon SLACK_WEBHOOK_URL)
# ---------------------------------------------------------------------------
step "3/4 — Envoi de la notification Slack (activités des 24 dernières heures)..."

"$PYTHON" main.py notify

# ---------------------------------------------------------------------------
# Étape 4 : Résumé final
# ---------------------------------------------------------------------------
step "4/4 — Résumé du pipeline après injection :"
"$PYTHON" main.py status

echo ""
ok "Démo terminée. Consultez Metabase sur http://localhost:3000"
