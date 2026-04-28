"""
NSXAI Core - Neuro-Symbolic Explainable AI Framework

This package contains the artificial intelligence layers:
- symbolic_layer: Logical reasoning and ontologies
- neural_layer: Machine learning
- neuro_symbolic_layer: Integration and explainability
"""

__version__ = "0.1.0-dev"
__author__ = "NSXAI Team"

from core.symbolic_layer import ontology_loader, knowledge_graph, inference_engine
from core.neural_layer import models, embeddings
from core.neuro_symbolic_layer import integration, explainability

__all__ = [
    "ontology_loader",
    "knowledge_graph",
    "inference_engine",
    "models",
    "embeddings",
    "integration",
    "explainability",
]
