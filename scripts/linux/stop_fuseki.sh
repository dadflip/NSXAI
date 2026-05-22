#!/bin/bash
# Arret de Jena Fuseki

echo ""
echo "========================================"
echo "  Arret de Jena Fuseki"
echo "========================================"
echo ""

# Trouver et arreter les processus Fuseki
PIDS=$(ps aux | grep '[f]useki' | awk '{print $2}')

if [ -z "$PIDS" ]; then
    echo "Aucun processus Fuseki en cours d'execution."
else
    for PID in $PIDS; do
        echo "Arret du processus Fuseki (PID: $PID)..."
        kill -9 $PID
    done
    echo ""
    echo "Fuseki arrete avec succes."
fi

echo ""
