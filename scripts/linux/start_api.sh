#!/bin/bash
# Demarrage de l'API Python NSXAI

echo ""
echo "========================================"
echo "  Demarrage de l'API NSXAI"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

# Verifier que le venv existe
if [ ! -d "venv" ]; then
    echo "ERREUR: Environnement virtuel non trouve"
    echo "Executez d'abord : ./scripts/linux/setup_venv.sh"
    exit 1
fi

# Activer le venv
source venv/bin/activate

# Lancer l'API
echo "Demarrage de l'API sur http://localhost:8000"
echo "Documentation : http://localhost:8000/api/docs"
echo ""
python -m nsxai.api.main
