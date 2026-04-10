# Architecture technique — POC Avantages Sportifs

## Vue d'ensemble

Ce document détaille les choix d'architecture pour le POC Avantages Sportifs de Sport Data Solution.

## Principes directeurs

1. **Simplicité** : ne pas empiler les technologies, choisir des outils multi-fonctions
2. **Maintenabilité** : code modulaire, tests à chaque niveau, documentation vivante
3. **Scalabilité** : chaque composant a un chemin de montée en charge identifié
4. **Sécurité** : données RH sensibles, accès contrôlé, pas d'exposition publique

## Flux de données

```
Sources (Excel, API, Simulation)
    │
    ▼
[Ingestion Python] ──▶ BRONZE (DuckDB, schéma bronze)
    │                      Données brutes, horodatées
    ▼
[Transformation Python + SODA] ──▶ SILVER (DuckDB, schéma silver)
    │                                  Données nettoyées, typées, validées
    ▼
[Business Python] ──▶ GOLD (DuckDB, schéma gold)
    │                    KPI, éligibilités, coûts, anomalies
    ▼
[Restitution]
    ├──▶ Metabase (dashboards)
    ├──▶ Slack (notifications)
    └──▶ Alertes (anomalies)
```

## Choix techniques détaillés

### DuckDB — Base de données

**Pourquoi DuckDB plutôt que PostgreSQL ou SQLite :**
- Moteur analytique (OLAP) optimisé pour les requêtes agrégées — parfait pour les KPI
- Zéro serveur : fichier unique, embarqué dans le process Python
- Lecture native des fichiers Excel, CSV, Parquet sans ETL externe
- SQL standard complet (window functions, CTEs, etc.)
- Organisation en schémas (bronze/silver/gold) dans un seul fichier
- Évolution naturelle vers MotherDuck (DuckDB cloud) sans changer le SQL

### Kestra — Orchestration

**Pourquoi Kestra plutôt qu'Airflow ou Prefect :**
- Un seul outil pour : orchestration, scheduling, monitoring, logs, alertes
- Flows déclarés en YAML (pas de code Python pour l'orchestration)
- UI web native pour la supervision et la démo live
- Variables d'environnement intégrées (paramètres dynamiques)
- Léger en ressources, démarrage rapide
- Pas besoin d'un outil de monitoring séparé

### Metabase — Visualisation

**Pourquoi Metabase plutôt que PowerBI ou Tableau :**
- Open-source, conteneurisable, pas de licence
- Connecteur DuckDB disponible (driver communautaire)
- Rafraîchissement automatique des données
- Démo live accessible via navigateur (localhost:3000)
- Alternative crédible en entreprise

### Docker Compose — Infrastructure

**Configuration des ports (évitement de conflits) :**
- Kestra UI : 8082 (interne 8080)
- Kestra API : 8083 (interne 8081)
- PostgreSQL Kestra : 5433 (interne 5432)
- Metabase : 3000

## Couche Bronze — Ingestion

### Module `src/ingestion/load_excel.py`

Deux fonctions principales, toutes deux basées sur `db_session` (gestionnaire de contexte DuckDB) :

| Fonction | Source | Table cible |
|----------|--------|-------------|
| `load_rh_to_bronze()` | `input/Donnees_RH.xlsx` | `bronze.rh_raw` |
| `load_sports_to_bronze()` | `input/Donnees_Sportive.xlsx` | `bronze.sports_raw` |

**Normalisation des colonnes :**
- Suppression des accents via `unicodedata.normalize("NFD")`
- Conversion en minuscules
- Remplacement des caractères non alphanumériques par `_`
- Exemples : `ID salarié` → `id_salarie`, `Prénom` → `prenom`, `Date d'embauche` → `date_d_embauche`

**Colonne technique ajoutée :** `_ingested_at` (timestamp UTC) sur chaque ligne.

**Création des tables :** `CREATE OR REPLACE TABLE` — idempotent, relançable sans effet de bord.

## Tests

### Stratégie à 3 niveaux

| Niveau | Outil | Cible | Exemple |
|--------|-------|-------|---------|
| Tâche Kestra | Assertions dans le flow | Chaque tâche produit un résultat | `bronze.rh_raw` contient 161 lignes |
| Qualité données | SODA Core | Couche Silver | Distance ≥ 0, dates valides |
| Unitaire | pytest | Fonctions Python | Calcul prime = salaire × 0.05 |

### Tests implémentés — Ingestion Bronze (`src/tests/test_ingestion.py`)

| Test | Table | Vérification |
|------|-------|--------------|
| `test_load_rh_row_count` | `bronze.rh_raw` | Exactement 161 lignes |
| `test_load_rh_columns_snake_case` | `bronze.rh_raw` | Colonnes `[a-z0-9_]+` uniquement |
| `test_load_rh_no_null_id` | `bronze.rh_raw` | Aucun `id_salarie` null |
| `test_load_rh_has_ingested_at` | `bronze.rh_raw` | `_ingested_at` présent et non null |
| `test_load_sports_row_count` | `bronze.sports_raw` | Exactement 161 lignes |
| `test_load_sports_no_null_id` | `bronze.sports_raw` | Aucun `id_salarie` null |

Chaque test utilise une DB temporaire (`/tmp/test_ingestion.duckdb`) nettoyée avant et après exécution.

## Sécurité

- Données RH non versionnées sur GitHub (`.gitignore`)
- Fichiers Excel dans `input/` (local uniquement)
- Variables sensibles (clés API) dans `.env` (non versionné)
- DuckDB en volume Docker local, pas d'exposition réseau
