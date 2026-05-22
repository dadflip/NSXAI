#!/bin/bash
# Raccourci Linux/Mac pour nsxai_cli.py
# Utilise le venv si present

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/nsxai_cli.py" "$@"
else
    echo "[WARN] venv non trouve - utilisation du Python systeme"
    echo "       Lancez d'abord : ./scripts/linux/setup_venv.sh"
    python3 "$SCRIPT_DIR/nsxai_cli.py" "$@"
fi
