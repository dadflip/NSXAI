#!/bin/bash
# NSXAI - Lanceur Linux/macOS
#
# Usage:
#   ./nsxai.sh dev       Demarre Fuseki, API et frontend Vite (superviseur au premier plan)
#   ./nsxai.sh start     Demarre Fuseki et l'API en arriere-plan
#   ./nsxai.sh stop      Arrete tous les services
#   ./nsxai.sh status    Affiche l'etat
#   ./nsxai.sh reset     Reinitialise la base de donnees

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/nsxai_cli.py" "$@"
else
    echo "[WARN] venv non trouve - utilisation du Python systeme"
    python3 "$SCRIPT_DIR/nsxai_cli.py" "$@"
fi
