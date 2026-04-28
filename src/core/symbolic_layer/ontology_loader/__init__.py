"""
Ontology Loader Module
Supports formats: OWL, RDF/XML, Turtle.
"""
from .loader import OntologyLoader, load_ontology, load_from_path

__all__ = [
    "OntologyLoader",
    "load_ontology",
    "load_from_path",
]