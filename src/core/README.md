# Core - NSXAI Framework Core

This folder contains the implementation of the three artificial intelligence layers.

## Structure

```
core/
├── __init__.py                    # Package initialization
├── symbolic_layer/                # Symbolic reasoning layer
│   ├── ontology_loader/           # OWL loading and parsing
│   ├── knowledge_graph/           # Knowledge graph (RDF/Neo4j)
│   ├── inference_engine/          # Logical inference engine
│   └── reasoning_rules/           # SWRL reasoning rules
│
├── neural_layer/                  # Neural learning layer
│   ├── models/                    # Architectures (MLP, GNN, Transformers)
│   ├── training/                  # Training and fine-tuning
│   ├── data_preprocessing/        # Data preparation
│   └── embeddings/                # Neural embeddings
│
├── neuro_symbolic_layer/        # Integration layer
│   ├── integration/               # Hybrid models and ontology/neural bridges
│   ├── explainability/            # Explainability (XAI)
│   ├── knowledge_distillation/    # Symbolic → neural distillation
│   ├── neural_symbolic_translation/ # Bidirectional translation
│   └── uncertainty_quantification/ # Uncertainty quantification
│
└── shared/                        # Shared resources
    ├── utils/                     # Utility functions
    ├── config/                    # Configuration (YAML/JSON)
    └── tests/                     # Unit and integration tests
```

## Usage

```python
from core import ontology_loader, knowledge_graph
from core.neural_layer import models
from core.neuro_symbolic_layer import explainability
```

## Tests

Tests are in the `tests/` folder at project root:

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v
```
