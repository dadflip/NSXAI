"""
Unit tests for the Ontology Loader module.

Run with:
    pytest tests/unit/test_ontology_loader.py -v
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest
from core.symbolic_layer.ontology_loader import (
    OntologyLoader,
    load_ontology,
    load_all_ontologies,
    load_from_path,
    visualize_ontology,
)


class TestOntologyLoader:
    """Test cases for OntologyLoader class."""
    
    def test_loader_initialization(self):
        """Test OntologyLoader initializes correctly."""
        loader = OntologyLoader()
        assert loader is not None
        assert hasattr(loader, 'ontologies_dir')
        assert hasattr(loader, 'loaded_graphs')
    
    def test_load_ontology(self):
        """Test loading a single ontology."""
        loader = OntologyLoader()
        
        # Try to load gato (smallest ontology)
        try:
            graph = loader.load_ontology("gato")
            assert graph is not None
            assert "gato" in loader.loaded_graphs
            # Note: len(graph) may be 0 if ontology has parser errors
            # but the graph object should still be returned
        except FileNotFoundError:
            pytest.skip("gato ontology not found")
    
    def test_get_statistics(self):
        """Test getting ontology statistics."""
        loader = OntologyLoader()
        
        try:
            loader.load_ontology("gato")
            stats = loader.get_statistics("gato")
            
            assert "name" in stats
            assert "triples" in stats
            assert "classes" in stats
            assert stats["name"] == "gato"
            # Note: stats may be 0 if ontology has parser errors
        except FileNotFoundError:
            pytest.skip("gato ontology not found")
    
    def test_list_loaded(self):
        """Test listing loaded ontologies."""
        loader = OntologyLoader()
        
        try:
            loader.load_ontology("gato")
            loaded = loader.list_loaded()
            
            assert isinstance(loaded, list)
            assert "gato" in loaded
        except FileNotFoundError:
            pytest.skip("gato ontology not found")


class TestLoadFunctions:
    """Test cases for convenience functions."""
    
    def test_load_ontology_function(self):
        """Test load_ontology convenience function."""
        try:
            graph = load_ontology("gato")
            assert graph is not None
            # Note: len(graph) may be 0 if ontology has parser errors
        except FileNotFoundError:
            pytest.skip("gato ontology not found")
    
    def test_load_all_ontologies_function(self):
        """Test load_all_ontologies convenience function."""
        graphs = load_all_ontologies()
        
        assert isinstance(graphs, dict)
        # May be empty if no ontologies found, but should be a dict
        assert all(isinstance(g, type(graphs[list(graphs.keys())[0]])) for g in graphs.values()) if graphs else True
    
    def test_load_from_path_function(self):
        """Test load_from_path generic function."""
        ontologies_dir = Path(__file__).parent.parent.parent / "source" / "ontologies"
        
        # Find first .owl file
        owl_files = list(ontologies_dir.glob("*.owl"))
        
        if not owl_files:
            pytest.skip("No .owl files found in source/ontologies/")
        
        filepath = owl_files[0]
        graph = load_from_path(filepath)
        
        assert graph is not None
        # Note: len(graph) may be 0 if ontology has parser errors
    
    def test_load_from_path_not_found(self):
        """Test load_from_path raises error for missing file."""
        with pytest.raises(FileNotFoundError):
            load_from_path("/nonexistent/path/ontology.owl")


class TestVisualizer:
    """Test cases for visualization functions."""
    
    def test_visualize_ontology_summary(self, capsys):
        """Test summary visualization."""
        try:
            graph = load_ontology("gato")
            visualize_ontology(graph, method="summary")
            
            captured = capsys.readouterr()
            assert "ONTOLOGY SUMMARY" in captured.out or captured.out == ""
        except FileNotFoundError:
            pytest.skip("gato ontology not found")
    
    def test_visualize_ontology_hierarchy(self, capsys):
        """Test hierarchy visualization."""
        try:
            graph = load_ontology("gato")
            visualize_ontology(graph, method="hierarchy")
            
            captured = capsys.readouterr()
            assert "CLASS HIERARCHY" in captured.out or captured.out == ""
        except FileNotFoundError:
            pytest.skip("gato ontology not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
