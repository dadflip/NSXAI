#!/bin/bash
# Script de reinitialisation complete de Fuseki

echo ""
echo "========================================"
echo "  Reinitialisation de Fuseki"
echo "========================================"
echo ""

cd "$(dirname "$0")/../.."

# Arreter Fuseki
echo "1. Arret de Fuseki..."
./scripts/linux/stop_fuseki.sh

sleep 2

# Supprimer les donnees
echo "2. Suppression des donnees..."
FUSEKI_RUN="triplestore/apache-jena-fuseki-5.1.0/run"

if [ -d "$FUSEKI_RUN/system" ]; then
    rm -rf "$FUSEKI_RUN/system"
    echo "   - system/ supprime"
fi

if [ -d "$FUSEKI_RUN/databases" ]; then
    rm -rf "$FUSEKI_RUN/databases"
    echo "   - databases/ supprime"
fi

echo ""
echo "========================================"
echo "  Fuseki reinitialise avec succes"
echo "========================================"
echo ""
echo "Vous pouvez maintenant redemarrer Fuseki :"
echo "  ./scripts/linux/start_fuseki.sh"
echo ""
