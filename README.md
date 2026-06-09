# NSXAI

Pipeline sémantique pour transformer des ontologies OWL/RDF en graphe de connaissances, avec triplestore Fuseki, API FastAPI et interface React pour exploration, requêtes SPARQL avancées et export ML.

> **🎉 Version 2.0** - Interface refondée avec éditeur SPARQL intelligent et design uniformisé

---

## 🚀 Nouveautés de la version 2.0

### ✨ Éditeur SPARQL amélioré
- **Autocomplétion intelligente** : Suggestions de mots-clés, classes, propriétés et individus
- **Bibliothèque de modèles** : 6 requêtes prêtes à l'emploi
- **Raccourcis clavier** : Ctrl+Enter pour exécuter, navigation au clavier
- **Interface moderne** : Design cohérent et intuitif

### 🎨 Design uniformisé
- Interface simplifiée (3 onglets au lieu de 4)
- Palette de couleurs cohérente
- Meilleure accessibilité

### 📚 Documentation complète
- **[INDEX_DOCUMENTATION.md](INDEX_DOCUMENTATION.md)** - Guide de navigation dans la documentation
- **[RESUME_MODIFICATIONS.md](RESUME_MODIFICATIONS.md)** - Résumé des changements en français
- **[nsxai/app/GUIDE_SPARQL.md](nsxai/app/GUIDE_SPARQL.md)** - Guide de l'éditeur SPARQL

---

## Prérequis

- Python 3.10 ou 3.11
- Node.js 18+ (frontend)
- Java 11+ (Apache Jena Fuseki, installé automatiquement au premier lancement)

---

## Démarrage rapide

### 1. Environnement Python

```bash
git clone https://github.com/your-org/NSXAI.git
cd NSXAI
python -m venv venv
```

**Linux / macOS**

```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Lancer la plateforme

**Linux / macOS**

```bash
chmod +x nsxai.sh
./nsxai.sh start
```

**Windows**

```cmd
nsxai.bat start
```

Au premier `start`, Jena Fuseki est téléchargé si nécessaire, le dataset est initialisé depuis `ontologies/owl/`, puis démarrent l’API et le frontend.

| Service   | URL par défaut              |
|-----------|-----------------------------|
| Frontend  | http://localhost:5173       |
| API       | http://localhost:8000     |
| Fuseki    | http://localhost:3030/nsxai |

### 3. Commandes CLI utiles

Le projet utilise un gestionnaire CLI unifié écrit en Python (`nsxai_cli.py`) qui gère nativement le cycle de vie de tous les processus, de manière 100% portable sur Windows, Linux et macOS.

**Exemples complets :**

```bash
# Lancer tous les services (Fuseki + API + Frontend)
./nsxai.sh dev       # Sous Linux / macOS
nsxai.bat dev        # Sous Windows

# Gérer les services individuellement
./nsxai.sh start fuseki     # Démarrer uniquement Fuseki
./nsxai.sh start api        # Démarrer uniquement l'API
./nsxai.sh start frontend   # Démarrer uniquement le frontend Vite
./nsxai.sh stop frontend    # Arrêter le frontend
./nsxai.sh stop all         # Arrêter tous les processus en cours
./nsxai.sh status           # Voir l'état des différents services
./nsxai.sh reset            # Réinitialiser les bases de données TDB de Fuseki
```

**Avantages du CLI Python :**
- Pas de dépendance à des scripts `.bat` ou `.sh` fragiles avec chemins absolus
- Graceful shutdown des processus (géré avec `psutil`)
- Interface unifiée et facile à maintenir

---

## Interface : mode triplet

L’onglet **Explorer** affiche une **arborescence unifiée** en cascade S-P-O :

- Un seul arbre (plus de sections « class / individual / property »).
- Chaque nœud et liaison conserve un **badge de type** (classe, propriété, individu, littéral).
- Les racines sont les sujets non référencés comme objets IRI dans le graphe.

Le bouton **Nouveau parcours** ouvre le modal **Node vers ontologie** :

1. Sujet racine (existant ou instanciation).
2. Enchaînement de triplets : prédicats proposés par requêtes SPARQL (`domain`, topologie, assertions).
3. Objets : sélection dans le graphe, instanciation, littéral, ou prédicat externe (ontologies RDF/XML importées).

Endpoints API associés :

- `GET /api/ontology/predicates/{subject}`
- `GET /api/ontology/objects/{subject}/{predicate}`
- `POST /api/ontology/path` — persistance du parcours

---

## Configuration

Fichier central : `config.yaml` (lu par `config.py` et `nsxai_cli.py`).

| Section      | Rôle |
|-------------|------|
| `jena`      | Version, chemins Fuseki, répertoire `run/` |
| `fuseki`    | URL, nom du dataset, timeout |
| `frontend`  | Hôte/port Vite, répertoire `nsxai/app` |
| `api`       | Hôte/port FastAPI, CORS |
| `ontologies`| Répertoire OWL source, config Fuseki |

### Exemple minimal

```yaml
fuseki:
  url: http://localhost:3030
  dataset: nsxai

api:
  host: localhost
  port: 8000

frontend:
  port: 5173
```

### Options avancées

**Changer le dataset Fuseki**

```yaml
fuseki:
  url: http://localhost:3030
  dataset: mon_dataset
  timeout: 60
```

Adapter `scripts/config/fuseki_config.ttl` et relancer `./nsxai.sh restart`.

**CORS pour un frontend distant**

```yaml
api:
  cors_origins:
    - http://localhost:5173
    - https://mon-domaine.example
```

**Ontologies sources**

```yaml
ontologies:
  owl_dir: ontologies/owl
  fuseki_config: scripts/config/fuseki_config.ttl
```

Placer les fichiers `.owl` / `.ttl` sous `owl_dir`, puis :

```bash
./nsxai.sh restart
# ou POST /api/ontology/reset depuis l’UI
```

**Version Jena / chemin d’installation**

```yaml
jena:
  version: "5.1.0"
  install_dir: triplestore
  download_url: "https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-{version}.zip"
```

**Frontend en production**

Construire avec l’URL de l’API :

```bash
cd nsxai/app
VITE_API_BASE=http://localhost:8000 npm run build
```

**Pipeline ML (hors UI)**

```bash
python main.py --step all --dim 64
```

Voir `config.yaml` à la racine pour `owl_dir`, `dirs.ttl`, `dirs.kg`, etc. (pipeline d’embeddings).

---

## Structure du dépôt

```
NSXAI/
├── config.yaml           # Configuration services + ontologies
├── config.py             # Loader de configuration central
├── requirements.txt      # Dépendances globales unifiées
├── nsxai_cli.py          # Orchestration Fuseki / API / frontend 100% Python
├── nsxai.sh / nsxai.bat  # Raccourcis CLI
├── nsxai/
│   ├── api/              # FastAPI + routes ontology/sparql/export
│   └── app/              # React (Explorer triplet, graphe, SPARQL, ETL)
├── ontologies/owl/       # Sources OWL
└── scripts/              # Scripts d'installation et chargement (install_fuseki, load_ontologies)
```

---

## Développement

```bash
# API seule
cd nsxai/api && uvicorn main:app --reload --port 8000

# Frontend seule (proxy /api → 8000)
cd nsxai/app && npm install && npm run dev
```

---

## Licence

MIT — voir [LICENSE](LICENSE).
