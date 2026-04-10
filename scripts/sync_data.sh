#!/usr/bin/env bash
# =============================================================================
# scripts/sync_data.sh — Synchronisation du DuckDB depuis le volume Docker
#
# Le fichier sports_poc.duckdb est stocké dans le volume Docker nommé
# kestra_data (pas de bind mount macOS → pas de deadlock).
# Ce script le copie vers ./data/ sur le host quand nécessaire
# (analyse locale, backup, debug).
#
# Usage :
#   chmod +x scripts/sync_data.sh
#   ./scripts/sync_data.sh
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CONTAINER="kestra-sports"
SRC_PATH="/app/data/sports_poc.duckdb"
DEST_DIR="./data"

mkdir -p "$DEST_DIR"

echo "Synchronisation du DuckDB depuis le volume Docker..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Erreur : le conteneur ${CONTAINER} n'est pas en cours d'exécution."
    echo "Lancez d'abord : docker-compose up -d"
    exit 1
fi

docker cp "${CONTAINER}:${SRC_PATH}" "${DEST_DIR}/sports_poc.duckdb"
echo "DuckDB synchronisé vers ${DEST_DIR}/sports_poc.duckdb"
