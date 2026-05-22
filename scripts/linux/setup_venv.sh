#!/bin/bash
# Creation et configuration de l'environnement virtuel Python

echo ""
echo "========================================"
echo "  Configuration environnement Python"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

# Verifier si venv existe deja
if [ -d "venv" ]; then
    echo "Environnement virtuel deja present."
    echo "Pour le recreer, supprimez d'abord le dossier venv/"
    echo ""
    echo "Pour activer l'environnement virtuel :"
    echo "  source venv/bin/activate"
    echo ""
    exit 0
fi

# Creer le venv
echo "1. Creation de l'environnement virtuel..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "ERREUR: Impossible de creer le venv"
    exit 1
fi
echo "   [OK]"

# Activer et installer les dependances
echo ""
echo "2. Installation des dependances..."
source venv/bin/activate

echo "   - Mise a jour de pip..."
pip install --upgrade pip --quiet

echo "   - Installation requirements.txt..."
pip install -r requirements.txt --quiet

echo "   - Installation requirements-api.txt..."
pip install -r requirements-api.txt --quiet

echo ""
echo "========================================"
echo "  Installation terminee"
echo "========================================"
echo ""
echo "Pour activer l'environnement virtuel :"
echo "  source venv/bin/activate"
echo ""
echo "Pour desactiver :"
echo "  deactivate"
echo ""
