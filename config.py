"""
config.py — Chargement et résolution de la configuration NSXAI
===============================================================
Point d'entrée unique pour lire config.yaml.
Tous les chemins sont résolus en absolus depuis l'emplacement du fichier YAML.

Usage
-----
    from config import load_config, PipelineConfig

    cfg = load_config()                  # cherche config.yaml à côté de ce fichier
    cfg = load_config("autre/config.yaml")

    cfg.owl_dir       # pathlib.Path absolu
    cfg.work_dir      # pathlib.Path absolu
    cfg.dirs.ttl      # pathlib.Path absolu  (work_dir/ttl)
    cfg.dirs.inferred # pathlib.Path absolu
    cfg.dirs.kg       # pathlib.Path absolu
    cfg.catalog       # pathlib.Path absolu ou None
    cfg.verbose       # bool
    cfg.quiet         # bool
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Optional

_DEFAULT_CONFIG = pathlib.Path(__file__).resolve().parent / "config.yaml"


@dataclass
class Dirs:
    ttl:      pathlib.Path
    inferred: pathlib.Path
    kg:       pathlib.Path


@dataclass
class PipelineConfig:
    owl_dir:  pathlib.Path
    work_dir: pathlib.Path
    dirs:     Dirs
    catalog:  Optional[pathlib.Path]
    verbose:  bool
    quiet:    bool


def load_config(path: str | pathlib.Path | None = None) -> PipelineConfig:
    """
    Charge config.yaml et résout tous les chemins en absolus.
    Lève FileNotFoundError si le fichier est introuvable.
    Lève ImportError si PyYAML n'est pas installé.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML manquant. Installez : pip install pyyaml"
        )

    cfg_path = pathlib.Path(path).resolve() if path else _DEFAULT_CONFIG
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config introuvable : {cfg_path}")

    base = cfg_path.parent
    raw  = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    owl_dir  = (base / raw.get("owl_dir",  "ontologies")).resolve()
    work_dir = (base / raw.get("work_dir", "output")).resolve()

    sub = raw.get("dirs", {})
    dirs = Dirs(
        ttl      = work_dir / sub.get("ttl",      "ttl"),
        inferred = work_dir / sub.get("inferred",  "inferred"),
        kg       = work_dir / sub.get("kg",        "kg"),
    )

    catalog_raw = raw.get("catalog")
    if catalog_raw:
        catalog = (owl_dir / catalog_raw).resolve()
        if not catalog.exists():
            catalog = None
    else:
        candidate = owl_dir / "catalog-v001.xml"
        catalog = candidate if candidate.exists() else None

    return PipelineConfig(
        owl_dir  = owl_dir,
        work_dir = work_dir,
        dirs     = dirs,
        catalog  = catalog,
        verbose  = bool(raw.get("verbose", False)),
        quiet    = bool(raw.get("quiet",   False)),
    )