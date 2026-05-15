#!/usr/bin/env python3
"""
main.py — Orchestrateur du pipeline NSXAI
==========================================
Lit config.yaml pour tous les chemins. Aucun chemin en argument.

Usage
-----
    python main.py --step owl2ttl
    python main.py --step infer
    python main.py --step kg
    python main.py --step gnn
    python main.py --step all

    --config PATH   Config YAML (défaut : ./config.yaml)
    --dim    INT    Dimension des embeddings GNN (défaut : 16)
    -v / -q         Override verbose / quiet
"""

import argparse
import pathlib
import sys

# Importabilité des sous-modules du package
_ROOT = pathlib.Path(__file__).resolve().parent
for _sub in ("nsxai/semantic", "nsxai/kg", "nsxai/gnn"):
    _p = _ROOT / _sub
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ── Étapes du pipeline ────────────────────────────────────────────────────────

def run_owl2ttl(cfg) -> list[pathlib.Path]:
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


def run_infer(cfg, ttl_files: list[pathlib.Path] | None = None) -> list[pathlib.Path]:
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


def run_kg(cfg, ttl_files: list[pathlib.Path] | None = None) -> None:
    from kg_builder import build_kg
    inputs = ttl_files or sorted(cfg.dirs.inferred.glob("*.ttl"))
    build_kg(
        ttl_files = inputs,
        out_dir   = cfg.dirs.kg,
        verbose   = cfg.verbose,
        quiet     = cfg.quiet,
    )


def run_gnn(cfg, dim: int = 16) -> None:
    from gnn_model import run_gnn as _run_gnn

    kg_dir    = cfg.dirs.kg
    nodes_csv = kg_dir / "nodes.csv"
    edges_csv = kg_dir / "edges.csv"

    # cfg.dirs.embeddings est optionnel — fallback propre si absent
    out_dir = getattr(cfg.dirs, "embeddings", None) or (
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
        description="Pipeline NSXAI : OWL → TTL → inférences → KG → embeddings GNN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--step",
        choices=["owl2ttl", "infer", "kg", "gnn", "all"],
        required=True,
        help="Étape à exécuter (all = chaîne complète)",
    )
    p.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="Fichier de configuration YAML (défaut : ./config.yaml)",
    )
    p.add_argument(
        "--dim", default=16, type=int, metavar="INT",
        help="Dimension des embeddings GNN (défaut : 16, step gnn/all uniquement)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Override verbose")
    p.add_argument("-q", "--quiet",   action="store_true", help="Override quiet")
    return p


def main() -> int:
    args = build_parser().parse_args()

    from config import load_config
    cfg = load_config(args.config)

    # Overrides CLI
    if args.verbose:
        cfg.verbose = True
    if args.quiet:
        cfg.quiet = True

    if args.step == "owl2ttl":
        run_owl2ttl(cfg)

    elif args.step == "infer":
        run_infer(cfg)

    elif args.step == "kg":
        run_kg(cfg)

    elif args.step == "gnn":
        run_gnn(cfg, dim=args.dim)

    elif args.step == "all":
        ttl_files = run_owl2ttl(cfg)
        inferred  = run_infer(cfg, ttl_files)
        run_kg(cfg, inferred)
        run_gnn(cfg, dim=args.dim)

    return 0


if __name__ == "__main__":
    sys.exit(main())