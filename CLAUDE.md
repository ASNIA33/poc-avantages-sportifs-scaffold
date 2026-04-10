# CLAUDE.md — Instructions pour Claude Code

## Projet
POC Avantages Sportifs — Sport Data Solution  
Pipeline data end-to-end pour calculer les avantages sportifs des salariés.

## Commandes fréquentes

```bash
# Lancer les tests
cd src && python -m pytest tests/ -v

# Lancer un module spécifique
python -m src.ingestion.load_excel

# Démarrer l'infra
docker-compose up -d

# Vérifier les conteneurs
docker-compose ps

# Voir les logs Kestra
docker-compose logs -f kestra

# Accéder à DuckDB en CLI
python -c "import duckdb; conn = duckdb.connect('data/sports_poc.duckdb'); print(conn.sql('SHOW TABLES').fetchall())"
```

## Stack technique

| Outil | Version | Rôle | Port |
|-------|---------|------|------|
| Python | 3.11+ | Pipeline ETL | — |
| DuckDB | latest | Base analytique (Bronze/Silver/Gold) | — |
| Kestra | latest | Orchestration + monitoring | 8082/8083 |
| Metabase | latest | Dashboards KPI | 3000 |
| PostgreSQL | 18 | Backend Kestra | 5433 |

## Architecture des données

```
Excel/API → [BRONZE] brut → [SILVER] nettoyé + testé → [GOLD] KPI métier
                DuckDB schema: bronze    silver              gold
```

### Schéma Bronze
- `bronze.rh_raw` : import brut Donnees_RH.xlsx
- `bronze.sports_raw` : import brut Donnees_Sportive.xlsx
- `bronze.distances_raw` : résultats bruts API Google Maps
- `bronze.strava_raw` : simulation activités sportives (12 mois)

### Schéma Silver
- `silver.employees` : RH nettoyé, typé, dédupliqué
- `silver.sports_activities` : sport corrigé (Runing→Running, etc.)
- `silver.distances` : distances validées domicile-bureau
- `silver.strava_activities` : activités normalisées

### Schéma Gold
- `gold.prime_eligibility` : éligibilité prime 5% + montant
- `gold.wellbeing_eligibility` : éligibilité jours bien-être
- `gold.cost_summary` : coût total par BU, par avantage
- `gold.distance_anomalies` : déclarations incohérentes
- `gold.activity_leaderboard` : classement activités par salarié

## Règles métier

### Prime sportive (5% du brut)
- Éligible si `moyen_deplacement` IN ('Marche/running', 'Vélo/Trottinette/Autres')
- ET distance domicile-bureau cohérente :
  - Marche/running : ≤ 15 km
  - Vélo/Trottinette : ≤ 25 km
- Adresse entreprise : `1362 Av. des Platanes, 34970 Lattes`
- Montant = salaire_brut × 0.05 (taux paramétrable)

### Jours bien-être (5 jours/an)
- Éligible si ≥ 15 activités physiques sur les 12 derniers mois
- Source : table strava_activities (simulation)
- Seuil paramétrable

## Git — Règles strictes

### ⛔ INTERDIT
- Commiter sur `main`
- Merger sur `main` (réservé au développeur)
- Ajouter Co-Authored-By

### ✅ OBLIGATOIRE
- Travailler sur `develop`
- Vérifier la branche AVANT chaque commit : `git branch --show-current`
- Commits atomiques au format Conventional Commits
- Format : `type(scope): description en français`
- Types : feat, fix, refactor, test, docs, chore, ci

### Exemples
```
feat(ingestion): ajout du chargement Excel RH avec insertion Bronze DuckDB
test(ingestion): ajout des tests unitaires pour le chargeur RH
fix(transformation): gestion des valeurs nulles dans le nettoyage des sports
docs(readme): ajout de la documentation des flows Kestra
chore(docker): mise à jour des ports pour éviter les conflits
```

## Tests

### Chaque tâche Kestra a son test
- Le test valide que la tâche a produit le résultat attendu
- Exemple : après ingestion RH → vérifier que `bronze.rh_raw` contient 161 lignes

### SODA (couche Silver)
- Fichier : `src/tests/soda/checks.yml`
- Checks : not null, valid range, uniqueness, referential integrity

### pytest (fonctions Python)
- Fichier par module : `test_ingestion.py`, `test_transformation.py`, etc.
- Tester les cas limites : 0 km, 50 km en marche, 14 vs 15 activités

## Logging
- Module : `src/utils/logger.py`
- Format : `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- Niveaux : INFO (défaut), WARNING (anomalies), ERROR (échecs)

## Tests — Règle absolue

### AUCUN COMMIT SANS TESTS VERTS
Ne JAMAIS commiter si un test échoue. Ne JAMAIS restituer un résultat au développeur tant qu'un bug persiste.
Workflow obligatoire :
1. Coder la fonctionnalité
2. Coder les tests
3. `python -m pytest -v`
4. Si FAIL → corriger → relancer → boucler jusqu'à 100% PASS
5. Quand tout est vert → commit
6. Restituer au développeur

## Diagrammes — Mermaid
- Utiliser la syntaxe Mermaid pour tous les diagrammes dans la documentation
- README.md : diagramme d'architecture global en Mermaid
- docs/architecture.md : diagrammes de flux détaillés par couche en Mermaid
- Mettre à jour les diagrammes à chaque évolution du pipeline

## Style de code
- PEP 8 strict
- Type hints sur toutes les fonctions
- Docstrings Google style
- SQL : mots-clés en MAJUSCULES, colonnes en snake_case
- Noms de fichiers : snake_case
