#!/usr/bin/env bash
# =============================================================================
# scripts/start.sh — Démarrage complet de l'infrastructure POC Avantages Sportifs
#
# Enchaîne :
#   1. Démarrage des conteneurs (PostgreSQL, Kestra, Metabase)
#   2. Attente du healthcheck Metabase
#   3. Exécution du pipeline Bronze → Silver → Gold
#   4. Affichage des URLs d'accès
#
# Usage :
#   chmod +x scripts/start.sh
#   ./scripts/start.sh
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[start.sh]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }

# ---------------------------------------------------------------------------
# 1. Démarrage des conteneurs
# ---------------------------------------------------------------------------
log "Démarrage de l'infrastructure Docker..."
docker-compose up -d postgres-sports kestra-sports metabase-sports

# ---------------------------------------------------------------------------
# 2. Attente du healthcheck Metabase (max 3 min)
# ---------------------------------------------------------------------------
log "Attente de Metabase (jusqu'à 3 minutes)..."
MAX_ATTEMPTS=36
ATTEMPT=0
until curl -sf http://localhost:3000/api/health > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
        warn "Metabase n'est pas prêt après ${MAX_ATTEMPTS} tentatives — vérifiez les logs :"
        warn "  docker-compose logs metabase-sports"
        break
    fi
    echo -n "."
    sleep 5
done
echo ""
ok "Metabase prêt."

# ---------------------------------------------------------------------------
# 3. Exécution du pipeline
# ---------------------------------------------------------------------------
log "Lancement du pipeline Bronze → Silver → Gold..."
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

"$PYTHON" main.py run
ok "Pipeline terminé."

# ---------------------------------------------------------------------------
# 4. Affichage des URLs
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  POC Avantages Sportifs — Infrastructure prête"
echo "============================================================"
echo "  Kestra UI   : http://localhost:8082"
echo "  Metabase    : http://localhost:3000"
echo "============================================================"
echo ""
log "Statut du pipeline :"
"$PYTHON" main.py status
