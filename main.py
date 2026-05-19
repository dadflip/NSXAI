#!/usr/bin/env python3
"""
main.py — Orchestrateur du pipeline NSXAI (pipeline complet)
=============================================================
Intègre les trois scripts de préparation ontologique dans le pipeline principal.

Étapes disponibles
------------------
  Préparation (génération de instances.owl) :
    extract   — Analyse les OWL sources -> schema.json + CSV templates vides
    populate  — Remplit les CSV avec des individus synthétiques
    build_owl — Injecte les CSV peuplés -> ontologies/instances.owl

  Pipeline NSXAI (traitement du KG) :
    owl2ttl   — Convertit les OWL (dont instances.owl) en Turtle
    infer     — Applique l'inférence sémantique HermiT
    kg        — Construit le graphe de connaissances (nodes.csv + edges.csv)
    gnn       — Génère les embeddings de noeuds

  Enchaînements :
    prepare   — extract + populate + build_owl  (génère instances.owl)
    pipeline  — owl2ttl + infer + kg + gnn      (ancien "all")
    all       — prepare + pipeline              (chaîne complète de bout en bout)

Usage
-----
    python main.py --step extract
    python main.py --step populate
    python main.py --step build_owl
    python main.py --step prepare
    python main.py --step owl2ttl
    python main.py --step infer
    python main.py --step kg
    python main.py --step gnn
    python main.py --step pipeline  --dim 64
    python main.py --step all       --dim 64

    --config PATH   Config YAML (défaut : ./config.yaml)
    --dim    INT    Dimension des embeddings GNN (défaut : 16)
    --seed   INT    Graine aléatoire pour populate (défaut : 42)
    -v / -q         Override verbose / quiet
"""

import argparse
import importlib.util
import pathlib
import sys

# ── Résolution du répertoire racine & sous-modules NSXAI ─────────────────────

_ROOT = pathlib.Path(__file__).resolve().parent
for _sub in ("nsxai/semantic", "nsxai/kg", "nsxai/gnn"):
    _p = _ROOT / _sub
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ── Helpers pour importer les scripts de préparation ─────────────────────────

def _import_script(name: str):
    """Importe un script *.py du répertoire racine comme module."""
    script_path = _ROOT / name
    if not script_path.exists():
        print(f"[ERREUR] Script introuvable : {script_path}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), script_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _banner(step: str, label: str) -> None:
    width = 60
    print(f"\n{'─' * width}")
    print(f"  >> [{step.upper()}]  {label}")
    print(f"{'─' * width}\n")


def _with_argv(argv: list, fn) -> None:
    """Exécute fn() après avoir temporairement remplacé sys.argv."""
    _orig, sys.argv = sys.argv, argv
    try:
        fn()
    finally:
        sys.argv = _orig


# ── Étapes de préparation (scripts 1, 2, 3) ──────────────────────────────────

def run_extract(cfg) -> None:
    """
    Étape 1 — 1_extract_schema.py
    Analyse les ontologies OWL sources et génère :
      - data/schema.json
      - data/templates/<Classe>.csv  (templates vides)
    """
    _banner("extract", "Extraction du schéma ontologique -> schema.json + CSV templates")
    script = _import_script("1_extract_schema.py")
    _with_argv(
        ["1_extract_schema.py",
         "--onto-dir", str(cfg.owl_dir),
         "--out-dir",  str(_ROOT / "data")],
        script.main,
    )


def run_populate(cfg, seed: int = 42) -> None:
    """
    Étape 2 — 2_populate.py
    Remplit les CSV templates avec des individus synthétiques réalistes.
    Lit  : data/schema.json + data/templates/<Classe>.csv
    Écrit: data/templates/<Classe>.csv (peuplés)
    """
    _banner("populate", "Peuplement des CSV avec des individus synthétiques")
    script = _import_script("2_populate.py")
    _with_argv(
        ["2_populate.py",
         "--schema",  str(_ROOT / "data" / "schema.json"),
         "--out-dir", str(_ROOT / "data" / "templates"),
         "--seed",    str(seed)],
        script.main,
    )


def run_build_owl(cfg) -> pathlib.Path:
    """
    Étape 3 — 3_csv_to_owl.py
    Injecte les CSV peuplés dans l'ontologie et sauvegarde instances.owl.
    Lit  : data/templates/*.csv + data/schema.json + ontologies/*.owl
    Écrit: ontologies/instances.owl
    """
    _banner("build_owl", "Injection CSV -> ontologies/instances.owl")
    script = _import_script("3_csv_to_owl.py")
    instances_out = str(cfg.owl_dir / "instances.owl")
    _with_argv(
        ["3_csv_to_owl.py",
         "--onto-dir",  str(cfg.owl_dir),
         "--templates", str(_ROOT / "data" / "templates"),
         "--schema",    str(_ROOT / "data" / "schema.json"),
         "--output",    instances_out],
        script.main,
    )
    return pathlib.Path(instances_out)


# ── Étapes du pipeline NSXAI ─────────────────────────────────────────────────

def run_owl2ttl(cfg) -> list:
    _banner("owl2ttl", "Conversion OWL -> Turtle")
    from owl2ttl import convert_files
    owl_files = sorted(cfg.owl_dir.glob("*.owl"))
    results   = convert_files(
        owl_files    = owl_files,
        out_dir      = cfg.dirs.ttl,
        catalog_path = cfg.catalog,
        verbose      = cfg.verbose,
        quiet        = cfg.quiet,
    )
    return [r.out_path for r in results if r.success]


def run_infer(cfg, ttl_files=None) -> list:
    _banner("infer", "Inférence sémantique HermiT")
    from hermit_infer import infer_files
    inputs  = ttl_files or sorted(cfg.dirs.ttl.glob("*.ttl"))
    results = infer_files(
        ttl_files = inputs,
        owl_dir   = cfg.owl_dir,
        out_dir   = cfg.dirs.inferred,
        verbose   = cfg.verbose,
        quiet     = cfg.quiet,
    )
    return [r.out_path for r in results if r.success]


def run_kg(cfg, ttl_files=None) -> None:
    _banner("kg", "Construction du Knowledge Graph -> nodes.csv + edges.csv")
    from kg_builder import build_kg
    inputs = ttl_files or sorted(cfg.dirs.inferred.glob("*.ttl"))
    build_kg(
        ttl_files = inputs,
        out_dir   = cfg.dirs.kg,
        verbose   = cfg.verbose,
        quiet     = cfg.quiet,
    )


def run_gnn(cfg, dim: int = 16) -> None:
    _banner("gnn", f"Génération des embeddings GNN (dim={dim})")
    from gnn_model import run_gnn as _run_gnn

    kg_dir    = cfg.dirs.kg
    nodes_csv = kg_dir / "nodes.csv"
    edges_csv = kg_dir / "edges.csv"
    out_dir   = getattr(cfg.dirs, "embeddings", None) or (
        pathlib.Path("output/embeddings").resolve()
    )

    result = _run_gnn(
        nodes_csv = nodes_csv,
        edges_csv = edges_csv,
        out_dir   = out_dir,
        dim       = dim,
        verbose   = cfg.verbose,
        quiet     = cfg.quiet,
    )

    if not result.success:
        print(f"[ERREUR] étape gnn : {result.error}", file=sys.stderr)
        sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main",
        description="Pipeline NSXAI complet : génération ontologie -> KG -> embeddings GNN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--step",
        choices=[
            "extract", "populate", "build_owl", "prepare",
            "owl2ttl", "infer", "kg", "gnn", "pipeline",
            "all",
        ],
        required=True,
        help="Étape à exécuter (voir docstring pour le détail)",
    )
    p.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="Fichier de configuration YAML (défaut : ./config.yaml)",
    )
    p.add_argument(
        "--dim", default=16, type=int, metavar="INT",
        help="Dimension des embeddings GNN (défaut : 16)",
    )
    p.add_argument(
        "--seed", default=42, type=int, metavar="INT",
        help="Graine aléatoire pour l'étape populate (défaut : 42)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Override verbose")
    p.add_argument("-q", "--quiet",   action="store_true", help="Override quiet")
    return p


def main() -> int:
    args = build_parser().parse_args()

    from config import load_config
    cfg = load_config(args.config)

    if args.verbose:
        cfg.verbose = True
    if args.quiet:
        cfg.quiet = True

    # ── Préparation ───────────────────────────────────────────────────────────
    if args.step == "extract":
        run_extract(cfg)

    elif args.step == "populate":
        run_populate(cfg, seed=args.seed)

    elif args.step == "build_owl":
        run_build_owl(cfg)

    elif args.step == "prepare":
        run_extract(cfg)
        run_populate(cfg, seed=args.seed)
        run_build_owl(cfg)

    # ── Pipeline NSXAI ────────────────────────────────────────────────────────
    elif args.step == "owl2ttl":
        run_owl2ttl(cfg)

    elif args.step == "infer":
        run_infer(cfg)

    elif args.step == "kg":
        run_kg(cfg)

    elif args.step == "gnn":
        run_gnn(cfg, dim=args.dim)

    elif args.step == "pipeline":
        ttl_files = run_owl2ttl(cfg)
        inferred  = run_infer(cfg, ttl_files)
        run_kg(cfg, inferred)
        run_gnn(cfg, dim=args.dim)

    # ── Tout ──────────────────────────────────────────────────────────────────
    elif args.step == "all":
        run_extract(cfg)
        run_populate(cfg, seed=args.seed)
        run_build_owl(cfg)
        ttl_files = run_owl2ttl(cfg)
        inferred  = run_infer(cfg, ttl_files)
        run_kg(cfg, inferred)
        run_gnn(cfg, dim=args.dim)

    return 0


if __name__ == "__main__":
    sys.exit(main())
