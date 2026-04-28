"""
Configuration pytest pour NSXAI
"""
import pytest
import sys
from pathlib import Path

# Ajouter src/ au path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def source_dir():
    """Retourne le chemin du dossier source."""
    return Path(__file__).parent.parent / "source"


@pytest.fixture
def data_dir():
    """Retourne le chemin du dossier data."""
    return Path(__file__).parent.parent / "data"
