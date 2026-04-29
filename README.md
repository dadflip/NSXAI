# NSXAI

**Version:** `0.1.0-dev`

**Neuro-Symbolic Explainable AI** - A hybrid AI framework combining symbolic reasoning (OWL ontologies) and neural learning, with a focus on explainability.

---

## Project Architecture (6 Main Folders)

```
NSXAI/
├── src/                               # Source code (entire application)
│   ├── core/                            # Neuro-symbolic AI layer
│   │   ├── symbolic_layer/              → Ontologies, KG, inference
│   │   │   ├── ontology_loader/
│   │   │   ├── knowledge_graph/
│   │   │   ├── inference_engine/
│   │   │   └── reasoning_rules/
│   │   ├── neural_layer/                → Neural learning
│   │   │   ├── models/, training/
│   │   │   ├── data_preprocessing/
│   │   │   └── embeddings/
│   │   ├── neuro_symbolic_layer/        → Integration & XAI
│   │   │   ├── integration/
│   │   │   │   ├── hybrid_models/
│   │   │   │   └── ontology_neural_bridge/
│   │   │   ├── explainability/
│   │   │   │   ├── symbolic_explanations/
│   │   │   │   ├── neural_attention_maps/
│   │   │   │   └── hybrid_xai/
│   │   │   ├── knowledge_distillation/
│   │   │   ├── neural_symbolic_translation/
│   │   │   └── uncertainty_quantification/
│   │   └── shared/                      → Utils, config
│   │
│   ├── api/                             # REST API (FastAPI)
│   │   ├── auth/, endpoints/, middleware/
│   │   ├── schemas/, core/, deps/
│   │   └── tests/
│   │
│   ├── web/                             # User interface
│   │   ├── src/, components/, pages/
│   │   ├── styles/, public/
│   │   └── README.md
│   │
│   └── scripts/                         # Utility scripts
│       ├── ci/                          → CI/CD scripts
│       └── release/                     → Versioning
│
├── public/                            # public resources (raw data)
│   ├── ontologies/                      → ITLT/ : OWL ontologies
│   │   ├── gado_core.owl                → Core GADO
│   │   ├── gado_full.owl                → Full GADO
│   │   ├── gato.owl                     → GATO ontology
│   │   ├── its.pedagogical.owl          → ITS pedagogical model
│   │   └── itsdomain.owl                → ITS domain
│   ├── ressources/                      → PDFs, documentation
│   └── notebooks/                       → Jupyter notebooks
│
├── data/                              # Generated/processed data
│   ├── raw/, processed/, external/
│   ├── experiments/                     → MLflow/TensorBoard logs
│   └── logs/                            → Log files
│
├── models/                            # Saved models
│   ├── checkpoints/                     → Training checkpoints
│   └── serialized/                      → Serialized models
│
├── tests/                             # Unified tests
│   ├── unit/                            → Unit tests
│   ├── integration/                     → Integration tests
│   └── e2e/                             → End-to-end tests
│
└── docs/                              # Documentation
    └── (Sphinx/MkDocs)

├── .github/workflows/                 # CI/CD GitHub Actions
├── pyproject.toml                     # Project config (replaces setup.py)
├── requirements.txt                   # Dependencies
├── VERSION                            # Current version
├── CHANGELOG.md                       # Changelog
├── CONTRIBUTING.md                    # Contribution guide
└── README.md                          # This file
```

---

## Dependencies & Tools

### Semantic Web & Graphs
| Package | Version | Usage |
|---------|---------|-------|
| **owlready2** | ≥0.46 | OWL ontology manipulation (primary) |
| **rdflib** | ≥7.0.0 | OWL/RDF parsing/manipulation |
| **py2neo** | ≥2021.2.4 | Neo4j interface (persistent KG) |
| **networkx** | ≥3.0 | Graph structure manipulation |
| **matplotlib** | ≥3.8.0 | Graph visualization |

### Machine Learning & Optimization
| Package | Version | Usage |
|---------|---------|-------|
| **scikit-learn** | ≥1.3.0 | Classic ML, metrics, preprocessing |
| **optuna** | ≥3.4.0 | Hyperparameter optimization (NAS) |

### Experiment Tracking & MLOps
| Package | Version | Usage |
|---------|---------|-------|
| **tensorboard** | ≥2.13.0 | Training visualization (graphs, scalars) |
| **wandb** | ≥0.16.0 | Weights & Biases - cloud exp tracking |
| **mlflow** | ≥2.8.0 | Model lifecycle management (registry) |
| **dvc** | ≥3.30.0 | Data Version Control - dataset versioning |

### Visualization
| Package | Version | Usage |
|---------|---------|-------|
| **matplotlib** | ≥3.8.0 | Static plots |
| **seaborn** | ≥0.13.0 | Advanced statistical visualization |
| **plotly** | ≥5.18.0 | Interactive visualizations |

### Utilities
| Package | Version | Usage |
|---------|---------|-------|
| **pandas** | ≥2.1.0 | Tabular data manipulation |
| **numpy** | ≥1.24.0 | Numerical computing |

---

## Quick Start

### 1. Load Ontologies & Generate Reports

```bash
python main.py
# Select option 1: Load ontologies and generate reports
```

This loads all ontologies and generates:
- `ontology_report.json` - Structured statistics
- `ontology_graph.txt` - Readable graph format

### 2. Interactive Graph Visualization

```bash
python main.py
# Select option 2: Interactive visualization
# Choose an ontology (1-5)
```

Features:
- **Zoom/Pan**: Navigate the graph with mouse
- **Node Density**: Adjust visibility (0.1-1.0)
- **Element Types**: Toggle classes/properties/individuals
- **Layouts**: Spring, circular, Kamada-Kawai, random
- **Color Coding**: Blue (classes), Red (properties), Green (individuals)

---

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Or install as editable package
pip install -e .

# With optional dependencies
pip install -e ".[dev,api]"
```

---

## Ontology Loader Features

### Core Functionality
- **Pure owlready2 Implementation**: Clean, focused ontology loading
- **Multiple Format Support**: OWL, RDF/XML, Turtle
- **Dependency Resolution**: Handles remote imports gracefully
- **Error Handling**: Robust fallback mechanisms

### Report Generation
- **JSON Reports**: Structured statistics for programmatic use
- **Graph Reports**: Human-readable text format with hierarchies
- **Interactive Visualization**: Zoomable, pannable graph explorer

### Available Ontologies
| Ontology | Description | Triples | Classes | Properties |
|----------|-------------|---------|---------|------------|
| **gato** | Gamification patterns | 34 | 4 | 8 |
| **gado_core** | Core adaptive model | 668 | 48 | 21 |
| **gado_full** | Full adaptive model | 562 | 51 | 32 |
| **its.pedagogical** | Learning strategies | 169 | 11 | 31 |
| **itsdomain** | Domain concepts | 1214 | 66 | 178 |

---

## ITLT Ontologies

The OWL ontologies in `source/ontologies/` describe the **Intelligent Tutoring** domain:
- **GADO** : Adaptive diagnostic model (core + full)
- **GATO** : Task/pedagogical patterns ontology
- **ITS Pedagogical** : Adaptive learning strategies
- **ITS Domain** : Domain concepts being taught

These ontologies feed the **symbolic layer** for logical reasoning and explainability.

---

## Data Flow (Overview)

```
OWL Ontologies (ITLT)
       ↓
[Symbolic Layer] ──→ Knowledge Graph ──→ Inference Engine
       ↓                                        ↓
[Neural Layer] ────→ Embeddings ───────→ Hybrid Models
       ↓                                        ↓
[Neuro-Symbolic] ←── Explanation ←─────── Prediction
       ↓
  Hybrid XAI Output
```

---

## Contributing & Versioning

To contribute to the project or manage versions, see the complete guide:

📄 **[CONTRIBUTING.md](CONTRIBUTING.md)**

### Quick Summary

**Versioning** : `bump-my-version` with Semantic Versioning (`MAJOR.MINOR.PATCH[-prerelease]`)

**Git Workflow** : `feature/*` → `develop` → `main` → tag `v*` → Auto Release

**CI/CD** : GitHub Actions (tests, lint, coverage) + Automatic Release

---

## License

See `LICENSE`
