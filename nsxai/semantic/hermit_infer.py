#!/usr/bin/env python3
"""
hermit_infer.py — Inférence HermiT sur des fichiers Turtle (.ttl)
==================================================================
Utilisable en CLI ou importé comme module dans un pipeline.

Usage CLI
---------
    python hermit_infer.py [OPTIONS] [FILE.ttl ...]

    --owl-dir DIR   Dossier contenant les .owl + catalog (requis)
    --all DIR       Traiter tous les *.ttl d'un dossier
    --out DIR       Dossier de sortie (défaut : ./output)
    --dry-run       Affiche sans écrire
    -q / --quiet    Silencieux
    -v / --verbose  Détaillé

Usage module
------------
    from hermit_infer import infer_files, InferResult

    results = infer_files(
        ttl_files=["output/gato.ttl"],
        owl_dir="ontologies/",
        out_dir="output/inferred/",
    )
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys
import urllib.request
import urllib.response
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

INFERRED_SECTION_MARKER = "# -- INFERRED BY HermiT"
INFERRED_END_MARKER     = "# -- END INFERRED"


# ── Types publics ─────────────────────────────────────────────────────────────

@dataclass
class InferResult:
    ttl_path: pathlib.Path
    out_path: Optional[pathlib.Path] = None
    added: int = 0
    skipped: int = 0
    success: bool = False
    error: Optional[str] = None


# ── Chargement du world + HermiT ─────────────────────────────────────────────

def _load_world(owl_dir: pathlib.Path, log):
    import owlready2

    catalog_path = owl_dir / "catalog-v001.xml"
    catalog: dict[str, pathlib.Path] = {}

    if catalog_path.exists():
        ns = {"c": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
        root = ET.parse(catalog_path).getroot()
        for el in root.findall(".//c:uri", ns):
            iri   = el.get("name", "").rstrip("/")
            local = el.get("uri", "")
            if iri and local:
                p = (owl_dir / local).resolve()
                catalog[iri]       = p
                catalog[iri + "/"] = p
        log(2, f"  Catalog : {len(catalog) // 2} entree(s)")

        _orig = urllib.request.urlopen
        def _local_open(url_or_req, *a, **kw):
            url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
            iri = url.rstrip("/")
            if iri in catalog and catalog[iri].exists():
                data = catalog[iri].read_bytes()
                return urllib.response.addinfourl(io.BytesIO(data), {}, url, 200)
            return _orig(url_or_req, *a, **kw)
        try:
            import owlready2.namespace as _ns_mod
            _ns_mod.urllib.request.urlopen = _local_open
        except Exception:
            pass

    owlready2.onto_path.clear()
    owlready2.onto_path.append(str(owl_dir))

    world = owlready2.World()
    owl_files = sorted(owl_dir.glob("*.owl"))
    stubs  = [f for f in owl_files if "stub" in f.name.lower()]
    others = [f for f in owl_files if f not in stubs]

    for owl_file in stubs + others:
        try:
            world.get_ontology(owl_file.as_uri()).load()
            log(2, f"  Charge : {owl_file.name}")
        except Exception as exc:
            log(2, f"  [AVERT] {owl_file.name} : {exc}")

    log(1, "  Lancement de HermiT ...")
    try:
        with world:
            owlready2.sync_reasoner_hermit(world, infer_property_values=True)
        log(1, "  HermiT termine")
    except Exception as exc:
        log(1, f"  [AVERT] HermiT degrade : {exc}")

    return world


# ── Collecte des triplets inférés ─────────────────────────────────────────────

def _collect_inferences(world, ttl_file: pathlib.Path, log) -> list[tuple[str, str, str]]:
    import rdflib

    g_src = rdflib.Graph()
    g_src.parse(ttl_file, format="turtle")
    src_subjects = {str(s) for s in g_src.subjects() if isinstance(s, rdflib.URIRef)}

    inferred: list[tuple[str, str, str]] = []

    for onto in world.ontologies.values():
        for cls in onto.classes():
            if cls.iri not in src_subjects:
                continue
            for sup in cls.is_a:
                if hasattr(sup, "iri") and sup.iri and sup.iri != cls.iri:
                    inferred.append((cls.iri, "http://www.w3.org/2000/01/rdf-schema#subClassOf", sup.iri))
            for eq in getattr(cls, "equivalent_to", []):
                if hasattr(eq, "iri") and eq.iri and eq.iri != cls.iri:
                    inferred.append((cls.iri, "http://www.w3.org/2002/07/owl#equivalentClass", eq.iri))

        for ind in onto.individuals():
            if ind.iri not in src_subjects:
                continue
            for t in ind.INDIRECT_is_a:
                if hasattr(t, "iri") and t.iri:
                    inferred.append((ind.iri, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", t.iri))
            for same in getattr(ind, "equivalent_to", []):
                if hasattr(same, "iri") and same.iri and same.iri != ind.iri:
                    inferred.append((ind.iri, "http://www.w3.org/2002/07/owl#sameAs", same.iri))

    return inferred


# ── Helpers préfixes ──────────────────────────────────────────────────────────

def _prefixes_declared_in_text(text: str) -> set[str]:
    """Retourne l'ensemble des préfixes déclarés (@prefix xxx:) dans le texte TTL."""
    return set(re.findall(r'@prefix\s+(\w+)\s*:', text))


def _missing_prefixes(inf_body: str, g_inf: "rdflib.Graph", declared: set[str]) -> dict[str, str]:
    """
    Retourne {prefix: uri} pour les préfixes utilisés dans inf_body
    mais absents de declared (= préfixes du fichier TTL original).
    """
    missing: dict[str, str] = {}
    for prefix, ns in g_inf.namespaces():
        if prefix and f"{prefix}:" in inf_body and str(prefix) not in declared:
            missing[str(prefix)] = str(ns)
    return missing


# ── Ecriture du TTL enrichi ───────────────────────────────────────────────────

def _write_enriched(
    ttl_file: pathlib.Path,
    out_path: pathlib.Path,
    new_triples: list[tuple[str, str, str]],
    dry_run: bool,
    log,
) -> tuple[int, int]:
    import rdflib

    original = ttl_file.read_text(encoding="utf-8")

    if INFERRED_SECTION_MARKER in original:
        start = original.index(INFERRED_SECTION_MARKER)
        end   = original.find(INFERRED_END_MARKER, start)
        if end != -1:
            original = original[:start] + original[end + len(INFERRED_END_MARKER):].lstrip("\n")

    g_existing = rdflib.Graph()
    g_existing.parse(data=original, format="turtle")
    existing = {(str(s), str(p), str(o)) for s, p, o in g_existing}

    to_add  = [t for t in new_triples if t not in existing]
    skipped = len(new_triples) - len(to_add)

    if not to_add:
        log(2, f"  {ttl_file.name} : rien a ajouter ({skipped} deja presents)")
        return 0, skipped

    g_inf = rdflib.Graph()
    for prefix, ns in g_existing.namespaces():
        g_inf.bind(prefix, ns)
    for s, p, o in to_add:
        g_inf.add((rdflib.URIRef(s), rdflib.URIRef(p), rdflib.URIRef(o)))

    inf_ttl   = g_inf.serialize(format="turtle")
    inf_lines = [ln for ln in inf_ttl.splitlines() if not ln.strip().startswith("@prefix")]
    inf_body  = "\n".join(ln for ln in inf_lines if ln.strip())

    # ── CORRECTIF : injecter les préfixes manquants dans l'en-tête ────────────
    # inf_body peut utiliser des préfixes (ex: rdfs:) absents du TTL original.
    # On les détecte en comparant avec les déclarations textuelles de l'original,
    # pas avec g_existing.namespaces() (qui inclut les namespaces par défaut de rdflib).
    declared_in_original = _prefixes_declared_in_text(original)
    missing = _missing_prefixes(inf_body, g_inf, declared_in_original)
    if missing:
        inject = "\n".join(
            f"@prefix {p}: <{u}> ." for p, u in sorted(missing.items())
        )
        log(2, f"  {ttl_file.name} : injection préfixes manquants : {sorted(missing)}")
        original = inject + "\n" + original
    # ── fin correctif ─────────────────────────────────────────────────────────

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    section = (
        f"\n\n{INFERRED_SECTION_MARKER} - {timestamp} ({len(to_add)} triplet(s))"
        f" ------------------------------\n"
        f"{inf_body}\n"
        f"{INFERRED_END_MARKER} ------------------------------------------------------------------\n"
    )
    enriched = original.rstrip() + section

    if dry_run:
        log(1, f"  [DRY-RUN] {ttl_file.name} : {len(to_add)} triplet(s) infere(s)")
        for s, p, o in to_add[:10]:
            log(1, f"    <{s}>  ->  <{p}>  ->  <{o}>")
        if len(to_add) > 10:
            log(1, f"    ... et {len(to_add) - 10} autre(s)")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(enriched, encoding="utf-8")

    return len(to_add), skipped


# ── API publique ──────────────────────────────────────────────────────────────

def infer_files(
    ttl_files: list,
    owl_dir,
    out_dir = "output",
    dry_run: bool = False,
    verbose: bool = False,
    quiet: bool = False,
) -> list[InferResult]:
    """
    Applique HermiT sur une liste de fichiers TTL et ecrit les TTL enrichis.

    Parametres
    ----------
    ttl_files : chemins vers les .ttl a enrichir
    owl_dir   : dossier contenant les .owl sources + catalog
    out_dir   : dossier de sortie
    dry_run   : si True, n'ecrit rien sur disque
    verbose   : logs detailles
    quiet     : supprime tous les logs sauf erreurs

    Retourne
    --------
    Liste de InferResult (un par fichier).
    """
    try:
        import owlready2  # noqa: F401
        import rdflib     # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"Dependance manquante : {exc}\n"
            "Installez : pip install owlready2 rdflib"
        ) from exc

    ttl_paths = [pathlib.Path(f).resolve() for f in ttl_files]
    ttl_paths = [f for f in ttl_paths if f.exists()]
    owl_path  = pathlib.Path(owl_dir).resolve()
    out_path  = pathlib.Path(out_dir).resolve()

    log_level = 0 if quiet else (2 if verbose else 1)
    def log(level: int, msg: str) -> None:
        if log_level >= level:
            print(msg, flush=True)

    if not ttl_paths:
        log(1, "[AVERT] Aucun fichier .ttl valide trouve.")
        return []

    log(1, f"Chargement des ontologies OWL depuis {owl_path} ...")
    world = _load_world(owl_path, log)

    log(1, f"\nEnrichissement de {len(ttl_paths)} fichier(s) TTL -> {out_path}\n")

    results: list[InferResult] = []
    for ttl_file in ttl_paths:
        result = InferResult(ttl_path=ttl_file)
        dest   = out_path / ttl_file.name
        try:
            triples = _collect_inferences(world, ttl_file, log)
            added, skipped = _write_enriched(ttl_file, dest, triples, dry_run, log)
            result.out_path = dest
            result.added    = added
            result.skipped  = skipped
            result.success  = True
            log(1, f"  ok {ttl_file.name:<38}  +{added} infere(s), {skipped} deja presents")
        except Exception as exc:
            result.error = str(exc)
            log(0, f"  ERREUR {ttl_file.name} : {exc}")
        results.append(result)

    ok   = sum(1 for r in results if r.success)
    fail = len(results) - ok
    log(1, f"\nTermine : {ok} enrichi(s), {fail} echec(s).")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hermit_infer",
        description="Applique HermiT sur des TTL et ecrit les triplets inferes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("files", nargs="*", metavar="FILE.ttl",
                   help="Fichiers .ttl explicites (prioritaire sur la config)")
    p.add_argument("--config",  default="config.yaml", metavar="PATH",
                   help="Config YAML (défaut : ./config.yaml)")
    p.add_argument("--owl-dir", default=None, metavar="DIR")
    p.add_argument("--ttl-dir", default=None, metavar="DIR",
                   help="Dossier source TTL (override config.dirs.ttl)")
    p.add_argument("--out",     default=None, metavar="DIR")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet",   action="store_true")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    cfg = None
    try:
        from config import load_config
        cfg = load_config(args.config)
    except (FileNotFoundError, ImportError):
        pass

    owl_dir = pathlib.Path(args.owl_dir).resolve() if args.owl_dir else (cfg.owl_dir if cfg else None)
    ttl_dir = pathlib.Path(args.ttl_dir).resolve() if args.ttl_dir else (cfg.dirs.ttl if cfg else None)
    out_dir = pathlib.Path(args.out).resolve()     if args.out     else (cfg.dirs.inferred if cfg else pathlib.Path("output/inferred").resolve())
    verbose = args.verbose or (cfg.verbose if cfg else False)
    quiet   = args.quiet   or (cfg.quiet   if cfg else False)

    if not owl_dir:
        print("[ERREUR] owl-dir requis (via config.yaml ou --owl-dir).")
        return 1

    if args.files:
        ttl_files = [pathlib.Path(f) for f in args.files]
    elif ttl_dir and ttl_dir.exists():
        ttl_files = sorted(ttl_dir.glob("*.ttl"))
    else:
        print("Aucun fichier .ttl trouve. Verifiez config.dirs.ttl ou passez des FILE.")
        return 1

    try:
        results = infer_files(
            ttl_files = ttl_files,
            owl_dir   = owl_dir,
            out_dir   = out_dir,
            dry_run   = args.dry_run,
            verbose   = verbose,
            quiet     = quiet,
        )
    except ImportError as exc:
        print(f"[ERREUR] {exc}")
        return 1

    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())