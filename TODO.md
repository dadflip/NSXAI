# 📝 TODO - Prochaines étapes NSXAI

## ✅ Terminé

### Phase 1 : Apache Jena Fuseki
- [x] Installation automatique de Fuseki 5.1.0
- [x] Configuration du dataset `nsxai` avec TDB2
- [x] Scripts de démarrage/arrêt (Windows + Linux)
- [x] Script de test de connexion
- [x] Documentation complète

### Phase 2 : Backend Python FastAPI
- [x] Structure de l'API créée (`nsxai/api/`)
- [x] Client Fuseki implémenté
- [x] Routes SPARQL de base
- [x] Configuration CORS
- [x] Scripts de démarrage
- [x] Environnement virtuel Python
- [x] Documentation API (Swagger)

---

## 🚧 En cours - Phase 3 : Migration complète

### 1. Migrer les routes restantes de `server.ts`

#### 1.1 Architecture ontologie
```python
# À créer : nsxai/api/routes/ontology.py

@router.get("/api/ontology/architecture")
async def get_architecture():
    """
    Retourne :
    - classes (avec labels, comments, subClassOf)
    - properties (avec domains, ranges)
    - imports
    - individuals
    - individualLinks
    """
    # Utiliser des requêtes SPARQL via fuseki_client
    # Réutiliser les requêtes de server/services/sparql/*.rq
```

**Fichiers SPARQL à réutiliser :**
- `app/nsxai/server/services/sparql/get_classes.rq`
- `app/nsxai/server/services/sparql/get_properties.rq`
- `app/nsxai/server/services/sparql/get_individuals.rq`
- `app/nsxai/server/services/sparql/get_imports.rq`

#### 1.2 Gestion des triplets
```python
# À créer : nsxai/api/routes/triples.py

@router.post("/api/ontology/triples")
async def add_triples(triples: List[Triple]):
    """Ajouter des triplets au dataset"""
    # Construire une requête SPARQL INSERT
    # Utiliser fuseki_client.update()

@router.get("/api/ontology/triples")
async def get_triples():
    """Lister tous les triplets"""
    # SELECT ?s ?p ?o WHERE { ?s ?p ?o }
```

#### 1.3 Export ML
```python
# À créer : nsxai/api/routes/export.py

@router.get("/api/export/ml/triples")
async def export_ml_triples():
    """Export TSV pour ML (head, rel, tail)"""
    # Réutiliser la logique de server.ts
    # Ou mieux : appeler kg_builder.py

@router.get("/api/export/ml/encoded")
async def export_ml_encoded():
    """Export avec entity2id et relation2id"""

@router.get("/api/export/ml/mapping")
async def export_ml_mapping():
    """Export des mappings JSON"""

@router.get("/api/export/ml/negatives")
async def export_ml_negatives():
    """Export avec échantillons négatifs"""
```

#### 1.4 Validation SHACL
```python
# À créer : nsxai/api/routes/shacl.py

@router.post("/api/ontology/validate")
async def validate_shacl():
    """Valider le graphe avec SHACL"""
    # Utiliser pyshacl (déjà dans requirements-api.txt)
    # Récupérer le graphe depuis Fuseki
    # Appliquer les shapes SHACL

@router.get("/api/ontology/shacl-shapes")
async def list_shacl_shapes():
    """Lister les shapes SHACL"""

@router.post("/api/ontology/shacl-shapes")
async def create_shacl_shape():
    """Créer un shape SHACL"""

@router.delete("/api/ontology/shacl-shapes/{uri}")
async def delete_shacl_shape(uri: str):
    """Supprimer un shape SHACL"""
```

#### 1.5 Raisonneur
```python
# À créer : nsxai/api/routes/reasoner.py

@router.post("/api/reasoner/run")
async def run_reasoner():
    """Exécuter l'inférence"""
    # Option 1 : Utiliser hermit_infer.py
    # Option 2 : Implémenter des règles SPARQL simples

@router.get("/api/reasoner/rules")
async def list_rules():
    """Lister les règles d'inférence"""

@router.post("/api/reasoner/rules")
async def add_rule():
    """Ajouter une règle d'inférence"""

@router.get("/api/reasoner/stats")
async def get_reasoner_stats():
    """Statistiques du raisonneur"""

@router.get("/api/reasoner/inferences")
async def list_inferences():
    """Lister les triplets inférés"""
```

### 2. Adapter le frontend

#### 2.1 Changer l'URL de base
```typescript
// app/nsxai/src/App.tsx

// AVANT
const API_URL = "http://localhost:3000";

// APRÈS
const API_URL = "http://localhost:8000";
```

#### 2.2 Tester chaque fonctionnalité
- [ ] Visualisation du graphe
- [ ] Requêtes SPARQL
- [ ] Export ML
- [ ] Validation SHACL
- [ ] Raisonneur
- [ ] Gestion des triplets

### 3. Charger les ontologies dans Fuseki

```python
# À créer : scripts/load_to_fuseki.py

"""
Script pour charger les ontologies dans Fuseki
1. Lire les fichiers OWL depuis ontologies/
2. Convertir en TTL (réutiliser owl2ttl.py)
3. Charger dans Fuseki via fuseki_client.load_ttl()
"""
```

### 4. Nettoyage

- [ ] Supprimer `app/nsxai/server.ts`
- [ ] Supprimer `app/nsxai/server/`
- [ ] Nettoyer `app/nsxai/package.json` :
  ```json
  {
    "scripts": {
      "dev": "vite",
      "build": "vite build",
      "preview": "vite preview"
    }
  }
  ```
- [ ] Supprimer les dépendances Node.js redondantes :
  - `oxigraph`
  - `@rdfjs/*`
  - `n3`
  - `rdf-validate-shacl`
  - `fast-xml-parser`
  - `@xmldom/xmldom`

---

## 📅 Planning suggéré

### Semaine 1 : Routes de base
- Jour 1-2 : Architecture ontologie
- Jour 3-4 : Gestion des triplets
- Jour 5 : Tests et debug

### Semaine 2 : Fonctionnalités avancées
- Jour 1-2 : Export ML
- Jour 3-4 : Validation SHACL
- Jour 5 : Raisonneur

### Semaine 3 : Intégration et nettoyage
- Jour 1-2 : Adapter le frontend
- Jour 3 : Charger les ontologies
- Jour 4-5 : Nettoyage et tests finaux

---

## 🎯 Priorités

### Haute priorité (à faire en premier)
1. **Architecture ontologie** - Le frontend en dépend fortement
2. **Gestion des triplets** - Fonctionnalité de base
3. **Charger les ontologies** - Pour avoir des données de test

### Moyenne priorité
4. **Export ML** - Important pour le pipeline
5. **Adapter le frontend** - Tester au fur et à mesure

### Basse priorité (peut attendre)
6. **Validation SHACL** - Fonctionnalité avancée
7. **Raisonneur** - Peut utiliser hermit_infer.py en attendant

---

## 🧪 Tests à faire

### Tests unitaires
```python
# À créer : tests/test_api.py

def test_sparql_query():
    """Test d'une requête SPARQL simple"""

def test_add_triples():
    """Test d'ajout de triplets"""

def test_fuseki_connection():
    """Test de connexion à Fuseki"""
```

### Tests d'intégration
```python
# À créer : tests/test_integration.py

def test_full_pipeline():
    """Test du pipeline complet OWL → Fuseki → API → Frontend"""
```

### Tests frontend
```typescript
// À créer : app/nsxai/src/__tests__/App.test.tsx

test('SPARQL query works', async () => {
  // Test d'une requête SPARQL via l'API
});
```

---

## 📚 Documentation à créer

- [ ] Guide de contribution (`CONTRIBUTING.md`)
- [ ] Guide de déploiement (`DEPLOYMENT.md`)
- [ ] Changelog (`CHANGELOG.md`)
- [ ] API Reference complète
- [ ] Tutoriels vidéo (optionnel)

---

## 🔧 Améliorations futures

### Performance
- [ ] Cache Redis pour les requêtes SPARQL fréquentes
- [ ] Pagination pour les grandes listes
- [ ] Compression des réponses API

### Sécurité
- [ ] Authentification JWT
- [ ] Rate limiting
- [ ] Validation des entrées SPARQL (injection)

### Fonctionnalités
- [ ] Import/Export de datasets complets
- [ ] Versioning des ontologies
- [ ] Historique des modifications
- [ ] Notifications en temps réel (WebSocket)

### DevOps
- [ ] Docker Compose pour tout le stack
- [ ] CI/CD (GitHub Actions)
- [ ] Monitoring (Prometheus + Grafana)
- [ ] Logs centralisés

---

## 💡 Conseils

1. **Commencer petit** : Migrer une route à la fois
2. **Tester souvent** : Vérifier chaque route avant de passer à la suivante
3. **Réutiliser** : Les modules Python existants sont déjà bien testés
4. **Documenter** : Mettre à jour la doc au fur et à mesure
5. **Git** : Commiter régulièrement avec des messages clairs

---

## 📞 Aide

Si vous êtes bloqué :
1. Consulter la documentation FastAPI : https://fastapi.tiangolo.com
2. Consulter la documentation Fuseki : https://jena.apache.org/documentation/fuseki2/
3. Regarder les exemples dans `server.ts` pour comprendre la logique
4. Tester les requêtes SPARQL dans l'interface Fuseki (http://localhost:3030)

---

**Dernière mise à jour** : 21 mai 2026, 23:15 CEST
