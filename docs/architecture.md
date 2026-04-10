# Architecture technique — POC Avantages Sportifs

## Vue d'ensemble

Ce document détaille les choix d'architecture pour le POC Avantages Sportifs de Sport Data Solution.

## Principes directeurs

1. **Simplicité** : ne pas empiler les technologies, choisir des outils multi-fonctions
2. **Maintenabilité** : code modulaire, tests à chaque niveau, documentation vivante
3. **Scalabilité** : chaque composant a un chemin de montée en charge identifié
4. **Sécurité** : données RH sensibles, accès contrôlé, pas d'exposition publique

## Flux de données

### Pipeline global — Sources → Bronze → Silver → Gold → Restitution

```mermaid
flowchart TD
    subgraph Sources["📥 Sources de données"]
        RH["Donnees_RH.xlsx\n161 salariés"]
        SP["Donnees_Sportive.xlsx\n161 lignes sport"]
        GM["API Google Maps\nDistances domicile-bureau"]
        ST["Simulation Strava\nActivités 12 mois"]
    end

    subgraph Ingestion["⚙️ Ingestion Python — src/ingestion/"]
        LE["load_excel.py\nload_rh_to_bronze()\nload_sports_to_bronze()"]
        FD["fetch_distances.py\nfetch_distances()"]
        GS["generate_strava.py\ngenerate_strava_data()"]
    end

    subgraph Bronze["🟫 BRONZE — schéma bronze (DuckDB)"]
        BR["bronze.rh_raw"]
        BS["bronze.sports_raw"]
        BD["bronze.distances_raw"]
        BT["bronze.strava_raw"]
    end

    subgraph Silver["🥈 SILVER — schéma silver (DuckDB)"]
        SE["silver.employees"]
        SSA["silver.sports_activities"]
        SD["silver.distances"]
        STA["silver.strava_activities"]
    end

    subgraph Gold["🥇 GOLD — schéma gold (DuckDB)"]
        GP["gold.prime_eligibility\nÉligibilité prime 5%"]
        GW["gold.wellbeing_eligibility\nÉligibilité jours bien-être"]
        GC["gold.cost_summary\nCoûts par BU"]
        GA["gold.distance_anomalies\nDéclarations incohérentes"]
        GL["gold.activity_leaderboard\nClassement activités"]
    end

    subgraph Restitution["📤 Restitution"]
        MB["Metabase\nDashboards KPI\nport 3000"]
        SL["Slack\nNotifications"]
        AL["Alertes\nAnomalies distance"]
    end

    RH --> LE --> BR
    SP --> LE --> BS
    GM --> FD --> BD
    ST --> GS --> BT

    BR & BS --> SE
    BS --> SSA
    BD --> SD
    BT --> STA

    SE & SSA & SD --> GP
    SE & STA --> GW
    GP & GW --> GC
    SD --> GA
    STA --> GL

    GP & GW & GC & GA & GL --> MB
    GP & GW --> SL
    GA --> AL
```

### Flux de tests — SODA + pytest + Kestra

```mermaid
flowchart LR
    subgraph Kestra["⚙️ Tests Kestra (par tâche)"]
        K1["Vérif. bronze.rh_raw\n= 161 lignes"]
        K2["Vérif. bronze.sports_raw\n= 161 lignes"]
        K3["Vérif. silver.employees\nno null, unicité"]
        K4["Vérif. gold.prime_eligibility\n> 0 éligibles"]
    end

    subgraph SODA["🔍 Tests SODA (couche Silver)"]
        S1["Distances ≥ 0"]
        S2["Dates valides\net logiques"]
        S3["Unicité id_salarie"]
        S4["Salaires 25k–80k €"]
        S5["Pas de nulls\nchamps critiques"]
    end

    subgraph Pytest["🧪 Tests pytest (src/tests/)"]
        subgraph Ing["test_ingestion.py"]
            P1["RH : 161 lignes\nsnake_case · no null id\n_ingested_at présent"]
            P2["Sports : 161 lignes\nno null id_salarie"]
            P3["Strava : >1000 lignes\ncolonnes · dates · distances\nno null · uniquement sportifs"]
        end
        subgraph Trans["test_transformation.py"]
            P4["Nettoyage Running\nRuning → Running"]
            P5["Distances validées\nmax 15km marche"]
        end
        subgraph Bus["test_business.py"]
            P6["Prime = salaire × 0.05"]
            P7["Seuil 14/15/16 activités"]
        end
        subgraph Notif["test_notifications.py"]
            P8["Format message Slack"]
        end
    end

    Bronze["🟫 BRONZE"] -->|after ingestion| Kestra
    Silver["🥈 SILVER"] -->|after transformation| SODA
    Bronze -->|unit tests| Pytest
    Silver -->|unit tests| Pytest
    Gold["🥇 GOLD"] -->|unit tests| Pytest
    Gold -->|after business| Kestra
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

**RH & Sportif (Excel → Bronze)**

| Test | Table | Vérification |
|---|---|---|
| `test_load_rh_row_count` | `bronze.rh_raw` | Exactement 161 lignes |
| `test_load_rh_columns_snake_case` | `bronze.rh_raw` | Colonnes `[a-z0-9_]+` uniquement |
| `test_load_rh_no_null_id` | `bronze.rh_raw` | Aucun `id_salarie` null |
| `test_load_rh_has_ingested_at` | `bronze.rh_raw` | `_ingested_at` présent et non null |
| `test_load_sports_row_count` | `bronze.sports_raw` | Exactement 161 lignes |
| `test_load_sports_no_null_id` | `bronze.sports_raw` | Aucun `id_salarie` null |

**Simulation Strava (génération → Bronze)**

| Test | Table | Vérification |
|---|---|---|
| `test_strava_generation_row_count` | `bronze.strava_raw` | > 1 000 lignes |
| `test_strava_columns` | `bronze.strava_raw` | 7 colonnes exactes |
| `test_strava_no_null_required` | `bronze.strava_raw` | `id_salarie`, `date_debut`, `sport_type` non nuls |
| `test_strava_distance_positive` | `bronze.strava_raw` | `distance_m` > 0 quand non nulle |
| `test_strava_duration_positive` | `bronze.strava_raw` | `temps_ecoule_s` > 0 |
| `test_strava_date_range` | `bronze.strava_raw` | Toutes les dates dans les 12 derniers mois |
| `test_strava_only_sportifs` | `bronze.strava_raw` | Uniquement des salariés avec sport déclaré |

**Distances domicile-bureau (haversine/API → Bronze)**

| Test | Table | Vérification |
|---|---|---|
| `test_distances_row_count` | `bronze.distances_raw` | Exactement 68 lignes (sportifs) |
| `test_distances_columns` | `bronze.distances_raw` | 5 colonnes exactes |
| `test_distances_positive` | `bronze.distances_raw` | Toutes distances > 0 km |
| `test_distances_mode_coherent` | `bronze.distances_raw` | Marche → walking, Vélo → bicycling |
| `test_distances_no_null` | `bronze.distances_raw` | `id_salarie` et `distance_km` non nuls |
| `test_haversine_lattes` | _(unitaire)_ | Lattes → distance < 5 km |
| `test_haversine_nimes` | _(unitaire)_ | Nîmes → distance > 30 km |

Chaque test utilise une DB temporaire (`/tmp/test_ingestion.duckdb`) nettoyée avant et après exécution.
Le mode simulation haversine est utilisé en test (pas d'appel API réelle).

## Docker Compose — Services, ports et volumes

```mermaid
graph TD
    subgraph Compose["docker-compose.yml"]
        subgraph Services["Services"]
            PG["postgres\nImage: postgres:18\nPort: 5433→5432\nRôle: backend Kestra"]
            KE["kestra\nImage: kestra/kestra:latest\nPort: 8082→8080\nPort: 8083→8081\nDépend de: postgres"]
            MB["metabase\nImage: metabase/metabase:latest\nPort: 3000→3000\nDépend de: kestra"]
        end

        subgraph Volumes["Volumes partagés"]
            VDB["duckdb-data\nfichier sports_poc.duckdb\npartagé Kestra ↔ Metabase"]
            VPG["postgres-data\ndonnées PostgreSQL Kestra"]
            VKE["kestra-data\nflows + plugins Kestra"]
        end
    end

    PG -- "données persistantes" --> VPG
    KE -- "données persistantes" --> VKE
    KE -- "accès DuckDB" --> VDB
    MB -- "accès DuckDB" --> VDB
    PG -.->|"backend metadata"| KE
    KE -.->|"source DuckDB"| MB
```

## Sécurité

- Données RH non versionnées sur GitHub (`.gitignore`)
- Fichiers Excel dans `input/` (local uniquement)
- Variables sensibles (clés API) dans `.env` (non versionné)
- DuckDB en volume Docker local, pas d'exposition réseau
