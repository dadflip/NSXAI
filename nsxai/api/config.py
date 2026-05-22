"""
nsxai/api/config.py
Delegue au loader central config.py a la racine du projet.
Conserve la compatibilite avec le code existant qui importe `config`.
"""
import sys
from pathlib import Path

# S'assurer que la racine du projet est dans le path
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config import cfg as config  # noqa: F401 — re-export

__all__ = ["config"]
