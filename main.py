#!/usr/bin/env python3
"""
NSXAI Main Entry Point

Loads ontologies and generates reports.
Run after installing the package: pip install -e .
"""

import sys
from pathlib import Path

# Add src to path for development without installation
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def main():
    """Load ontologies and generate reports."""
    print("\n" + "="*70)
    print("NSXAI - Ontology Loader")
    print("="*70)
    
    return load_and_generate_reports()


def load_and_generate_reports():
    """Load ontologies and generate combined report."""
    from core.symbolic_layer.ontology_loader import OntologyLoader
    from core.symbolic_layer.ontology_loader.loader import DEFAULT_ONTOLOGIES
    import json
    
    loader = OntologyLoader()
    
    print(f"\nDirectory: {loader.ontologies_dir}")
    print(f"Configured: {list(DEFAULT_ONTOLOGIES.keys())}")
    
    # Load all ontologies
    print("\n" + "-"*70)
    print("LOADING")
    print("-"*70)
    
    loaded = []
    for name, filename in DEFAULT_ONTOLOGIES.items():
        filepath = loader.ontologies_dir / filename
        
        if not filepath.exists():
            print(f"  [SKIP] {name}: File not found")
            continue
        
        try:
            graph = loader.load_ontology(name)
            if len(graph) > 0:
                print(f"  [OK]   {name}: {len(graph)} triples")
                loaded.append(name)
            else:
                print(f"  [WARN] {name}: Empty (parser errors)")
        except Exception as e:
            print(f"  [ERR]  {name}: {e}")
    
    # Generate simple text report
    print("\n" + "-"*70)
    print("GENERATING SIMPLE REPORT")
    print("-"*70)
    
    report_path = loader.generate_simple_report("docs/reports/ontology_report.txt")
    print(f"  Report: {report_path}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Loaded: {len(loaded)}/{len(DEFAULT_ONTOLOGIES)} ontologies")
    print(f"  Report: {report_path}")
    
    for name in loaded:
        stats = loader.get_statistics(name)
        print(f"\n  {name}:")
        print(f"    Triples: {stats.get('triples', 0)}")
        print(f"    Classes: {stats.get('classes', 0)}")
        print(f"    Properties: {stats.get('properties', 0)}")
    
    print("\n" + "="*70 + "\n")
    return 0 if loaded else 1


if __name__ == "__main__":
    sys.exit(main())
