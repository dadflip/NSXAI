# NSXAI — IA Neuro-Symbolique Explicable

Système hybride qui combine **ontologie OWL** et **GNN** pour produire des prédictions
explicables symboliquement.

## Architecture

```
Ontologie OWL
     │
     ▼
 HermiT (REST)          ← inférences OWL DL (types, hiérarchie, propriétés)
     │
     ▼
 KGBuilder              ← construit le Knowledge Graph
     │  ├── nodes.csv   ← nœuds Neo4j
     │  ├── edges.csv   ← arêtes Neo4j
     │  └── graph.gexf  ← graphe NetworkX / Gephi
     ▼
 GNNPredictor           ← GraphSAGE (PyG) ou sklearn (fallback)
     │  └── predictions.json
     ▼
 OntologyExplainer      ← justification symbolique de chaque prédiction
        └── explanations.json
```

## Démarrage rapide

```bash
# 1. Copier vos ontologies
cp /chemin/vers/*.owl ontologies/

# 2. Configurer (optionnel)
cp .env .env.local

# 3. Lancer le pipeline complet
docker compose up hermit gnn

# Résultats dans ./output/
#   nodes.csv         → nœuds du KG (importable dans Neo4j)
#   edges.csv         → arêtes du KG
#   graph.gexf        → graphe complet (Gephi / NetworkX)
#   predictions.json  → prédictions GNN par nœud
#   explanations.json → explications ontologiques
```

## Sans Docker (développement)

```bash
cd gnn
pip install -r requirements.txt

# Pipeline complet
python -m gnn.pipeline \
  --ontology ../ontologies/gato.owl \
  --hermit http://localhost:7777 \
  --output ../output

# Ou étape par étape en Python :
from gnn import KGBuilder, GNNPredictor, OntologyExplainer

builder = KGBuilder("ontologies/gato.owl", hermit_url="http://localhost:7777")
graph, nodes_df, edges_df = builder.build()

predictor = GNNPredictor(graph, nodes_df)
predictions = predictor.predict()

explainer = OntologyExplainer("http://localhost:7777", graph)
explanations = explainer.explain(predictions)
```

## Activer PyTorch Geometric (GNN complet)

Dans `gnn/requirements.txt`, décommentez :
```
torch==2.1.0
torch-geometric==2.4.0
```

Sans PyG, le système utilise automatiquement un fallback sklearn (PageRank + centralité).

## Importer dans Neo4j

```bash
neo4j-admin database import full \
  --nodes=output/nodes.csv \
  --relationships=output/edges.csv \
  --database=nsxai
```

## Exploration SPARQL (optionnel)

```bash
# Lance Fuseki + Nginx en plus
docker compose --profile sparql up
# → http://localhost:3030  (Fuseki)
# → http://localhost:9000/ontologies/  (fichiers OWL statiques)
```

## Structure du projet

```
nsxai/
├── ontologies/          # Fichiers OWL + TTL
├── hermit/              # Service REST HermiT (raisonneur OWL DL)
│   ├── hermit_api_server.py
│   ├── Dockerfile
│   └── requirements.txt
├── gnn/                 # Pipeline neuro-symbolique
│   ├── __init__.py
│   ├── pipeline.py      # Orchestrateur principal
│   ├── kg_builder.py    # Ontologie → Knowledge Graph
│   ├── gnn_model.py     # Prédictions GNN
│   ├── explainer.py     # Explicabilité ontologique
│   └── requirements.txt
├── output/              # Résultats générés
├── Dockerfile.gnn
├── docker-compose.yml
└── .env
```

## Principe neuro-symbolique

| Composant | Rôle | Type |
|-----------|------|------|
| Ontologie OWL | Structure du savoir | Symbolique |
| HermiT | Inférences logiques | Symbolique |
| GNN | Prédictions sur le graphe | Neuronal |
| OntologyExplainer | Justification des prédictions | Symbolique |

Le GNN dit **quoi** (prédiction + score).
L'ontologie dit **pourquoi** (types inférés, règles OWL activées).
