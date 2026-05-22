#!/bin/bash
# Charger les ontologies dans Fuseki

echo ""
echo "========================================"
echo "  Chargement des ontologies"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

# Activer le venv
source venv/bin/activate

# Lancer le script
python scripts/load_to_fuseki.py
