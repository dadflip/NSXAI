#!/usr/bin/env python3
"""
owl2ttl.py — Conversion OWL/XML → Turtle (.ttl)
=================================================
Convertit un ou plusieurs fichiers OWL en Turtle.
Résout les imports via un catalog-v001.xml (Protégé) si présent.

Utilisable :
  - En ligne de commande (standalone)
  - Importé comme module dans un pipeline

Usage CLI
---------
    python owl2ttl.py [OPTIONS] [FILE ...]

    --out DIR        Dossier de sortie  (défaut : ./output)
    --catalog PATH   Catalog XML Protégé (optionnel)
    --all DIR        Convertit tous les *.owl d'un dossier
    -q / --quiet     Aucune sortie sauf erreurs
    -v / --verbose   Informations détaillées

Usage module
------------
    from owl2ttl import convert_files, ConversionResult

    results = convert_files(
        owl_files=["onto.owl"],
        out_dir="output",
        catalog_path="catalog-v001.xml",   # optionnel
        verbose=False,
    )
    for r in results:
        if r.success:
            print(r.out_path, r.triple_count)
        else:
            print(r.error)
"""

from __future__ import annotations

import argparse
import io
import pathlib
import sys
import urllib.request
import urllib.response
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


# ── Types publics ─────────────────────────────────────────────────────────────

@dataclass
class ConversionResult:
    """Résultat de la conversion d'un fichier OWL."""
    owl_path: pathlib.Path
    out_path: Optional[pathlib.Path] = None
    triple_count: int = 0
    success: bool = False
    error: Optional[str] = None


# ── Préfixes standards ────────────────────────────────────────────────────────

STANDARD_PREFIXES: dict[str, str] = {
    "owl":  "http://www.w3.org/2002/07/owl#",
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

_PREFIX_SKIP = {"owl", "rdf", "rdfs", "xsd", "xml"}


# ── Préfixes dynamiques ───────────────────────────────────────────────────────

def _extract_prefixes(owl_files: list[pathlib.Path]) -> dict[str, str]:
    """Extrait les déclarations <Prefix> depuis les fichiers OWL."""
    prefixes: dict[str, str] = {}
    for owl_file in owl_files:
        try:
            root = ET.parse(owl_file).getroot()
            for elem in root.iter():
                local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if local == "Prefix":
                    name = (elem.get("name") or "").rstrip(":")
                    iri  = elem.get("IRI", "")
                    if name and iri and name not in _PREFIX_SKIP:
                        prefixes[name] = iri
        except ET.ParseError:
            pass
    return prefixes


# ── Catalog Protégé ───────────────────────────────────────────────────────────

def _load_catalog(catalog_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Charge un catalog-v001.xml Protégé → {IRI: chemin_local}."""
    ns = {"c": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
    tree = ET.parse(catalog_path)
    root = tree.getroot()
    base = catalog_path.parent
    mapping: dict[str, pathlib.Path] = {}
    for uri_el in root.findall(".//c:uri", ns):
        iri   = uri_el.get("name", "").rstrip("/")
        local = uri_el.get("uri", "")
        if iri and local:
            abs_path = (base / local).resolve()
            mapping[iri]        = abs_path
            mapping[iri + "/"]  = abs_path
    return mapping


def _detect_stubs(
    catalog: dict[str, pathlib.Path],
    convert_set: set[pathlib.Path],
) -> list[pathlib.Path]:
    """Retourne les fichiers du catalog qui ne font pas partie de la conversion (imports)."""
    stubs, seen = [], set()
    for fpath in catalog.values():
        r = fpath.resolve()
        if r in convert_set or not fpath.exists() or r in seen:
            continue
        seen.add(r)
        stubs.append(fpath)
    return stubs


def _install_catalog_opener(catalog: dict[str, pathlib.Path]) -> None:
    """Redirige urllib vers les fichiers locaux du catalog."""
    try:
        import owlready2.namespace as _ns_mod
    except ImportError:
        return

    _original = urllib.request.urlopen

    def _catalog_urlopen(url_or_req, *args, **kwargs):
        url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
        iri = url.rstrip("/")
        if iri in catalog:
            data = catalog[iri].read_bytes()
            return urllib.response.addinfourl(io.BytesIO(data), {}, url, 200)
        return _original(url_or_req, *args, **kwargs)

    _ns_mod.urllib.request.urlopen = _catalog_urlopen  # type: ignore[attr-defined]


# ── Recherche d'ontologie dans le world owlready2 ─────────────────────────────

def _find_onto(world, owl_file: pathlib.Path):
    """Recherche une ontologie déjà chargée dans le world par URI ou base IRI."""
    file_uri = owl_file.as_uri()
    for candidate in (file_uri, file_uri + "#", file_uri.rstrip("/") + "#"):
        onto = world.ontologies.get(candidate)
        if onto is not None:
            return onto
    try:
        root = ET.parse(owl_file).getroot()
        base_iri = (
            root.get("xml:base")
            or root.get("{http://www.w3.org/XML/1998/namespace}base", "")
        )
        if base_iri:
            for candidate in (base_iri, base_iri + "#", base_iri.rstrip("/") + "#"):
                onto = world.ontologies.get(candidate)
                if onto is not None:
                    return onto
    except ET.ParseError:
        pass
    return None


# ── Conversion d'un fichier ───────────────────────────────────────────────────

def _convert_one(
    world,
    owl_file: pathlib.Path,
    out_dir: pathlib.Path,
    extra_prefixes: dict[str, str],
    log,
) -> ConversionResult:
    """Convertit un seul fichier OWL en TTL. Retourne un ConversionResult."""
    import rdflib

    result = ConversionResult(owl_path=owl_file)
    log(2, f"  Chargement {owl_file.name} ...")

    onto = None
    try:
        onto = world.get_ontology(owl_file.as_uri()).load()
    except Exception as exc:
        log(1, f"  [AVERT] {owl_file.name} : {exc}")
        onto = _find_onto(world, owl_file)

    if onto is None:
        result.error = f"Impossible de charger {owl_file.name}"
        return result

    buf = io.BytesIO()
    try:
        onto.graph.save(buf, format="ntriples")
    except Exception as exc:
        result.error = f"Sérialisation échouée : {exc}"
        return result

    nt_bytes = buf.getvalue()
    if not nt_bytes.strip():
        result.error = "Aucun triplet produit"
        return result

    g = rdflib.Graph()
    g.parse(data=nt_bytes, format="ntriples")

    all_prefixes = {**STANDARD_PREFIXES, **extra_prefixes}
    for prefix, uri in all_prefixes.items():
        g.bind(prefix, rdflib.Namespace(uri))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{owl_file.stem}.ttl"
    out_path.write_text(g.serialize(format="turtle"), encoding="utf-8")

    result.out_path    = out_path
    result.triple_count = len(g)
    result.success      = True
    return result


# ── API publique ──────────────────────────────────────────────────────────────

def convert_files(
    owl_files: list[str | pathlib.Path],
    out_dir: str | pathlib.Path = "output",
    catalog_path: Optional[str | pathlib.Path] = None,
    verbose: bool = False,
    quiet: bool = False,
) -> list[ConversionResult]:
    """
    Convertit une liste de fichiers OWL en Turtle.

    Paramètres
    ----------
    owl_files    : chemins vers les fichiers .owl
    out_dir      : dossier de sortie (créé si absent)
    catalog_path : chemin vers catalog-v001.xml (optionnel)
    verbose      : active les logs détaillés
    quiet        : supprime tous les logs sauf erreurs

    Retourne
    --------
    Liste de ConversionResult (un par fichier).
    Lève ImportError si owlready2 ou rdflib sont manquants.
    """
    try:
        import owlready2
        import rdflib  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"Dépendance manquante : {exc}\n"
            "Installez : pip install owlready2 rdflib"
        ) from exc

    # Normalisation des chemins
    owl_paths = [pathlib.Path(f).resolve() for f in owl_files]
    owl_paths = [f for f in owl_paths if f.exists()]
    out_path  = pathlib.Path(out_dir).resolve()

    # Niveau de log : 0=quiet, 1=normal, 2=verbose
    log_level = 0 if quiet else (2 if verbose else 1)

    def log(level: int, msg: str) -> None:
        if log_level >= level:
            print(msg, flush=True)

    if not owl_paths:
        log(1, "[AVERT] Aucun fichier .owl valide trouvé.")
        return []

    # Catalog
    catalog: dict[str, pathlib.Path] = {}
    if catalog_path:
        cat = pathlib.Path(catalog_path).resolve()
        if cat.exists():
            catalog = _load_catalog(cat)
            log(1, f"Catalog : {cat.name}  ({len(catalog) // 2} entrées)")
        else:
            log(1, f"[AVERT] Catalog introuvable : {cat}")
    _install_catalog_opener(catalog)

    # Préfixes dynamiques
    extra_prefixes = _extract_prefixes(owl_paths)
    if verbose and extra_prefixes:
        log(2, f"Préfixes extraits ({len(extra_prefixes)}) : "
               + ", ".join(f"{k}:" for k in sorted(extra_prefixes)))

    # World owlready2 + stubs
    world = owlready2.World()
    owlready2.onto_path.insert(0, str(out_path.parent))

    convert_set = {f.resolve() for f in owl_paths}
    stubs = _detect_stubs(catalog, convert_set)
    if stubs:
        log(1, "Pré-chargement des stubs ...")
        for stub in stubs:
            try:
                world.get_ontology(stub.as_uri()).load()
                log(2, f"  stub OK : {stub.name}")
            except Exception as exc:
                log(1, f"  stub AVERT ({stub.name}) : {exc}")

    log(1, f"\nConversion de {len(owl_paths)} fichier(s) → {out_path}\n")

    results: list[ConversionResult] = []
    for owl_file in owl_paths:
        r = _convert_one(world, owl_file, out_path, extra_prefixes, log)
        results.append(r)
        if r.success:
            log(1, f"  ✓ {owl_file.name:<38}  {r.triple_count:>6} triplets  →  {r.out_path.name}")
        else:
            log(0, f"  ✗ {owl_file.name} : {r.error}")

    ok   = sum(1 for r in results if r.success)
    fail = len(results) - ok
    log(1, f"\nTerminé : {ok} converti(s), {fail} échec(s).")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="owl2ttl",
        description="Convertit des ontologies OWL/XML en Turtle (.ttl)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("files", nargs="*", metavar="FILE",
                   help="Fichiers .owl explicites (prioritaire sur la config)")
    p.add_argument("--config",  default="config.yaml", metavar="PATH",
                   help="Config YAML (défaut : ./config.yaml)")
    # Overrides optionnels — si absents, la config fait foi
    p.add_argument("--owl-dir", default=None, metavar="DIR")
    p.add_argument("--out",     default=None, metavar="DIR")
    p.add_argument("--catalog", default=None, metavar="PATH")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("-q", "--quiet",   action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Chargement config (tolère l'absence si tout est fourni en args)
    cfg = None
    try:
        from config import load_config
        cfg = load_config(args.config)
    except (FileNotFoundError, ImportError):
        pass

    # Résolution owl_dir, out_dir, catalog (args > config > défauts)
    owl_dir  = pathlib.Path(args.owl_dir).resolve() if args.owl_dir else (cfg.owl_dir  if cfg else None)
    out_dir  = pathlib.Path(args.out).resolve()     if args.out     else (cfg.dirs.ttl if cfg else pathlib.Path("output/ttl").resolve())
    catalog  = args.catalog or (str(cfg.catalog) if cfg and cfg.catalog else None)
    verbose  = args.verbose or (cfg.verbose if cfg else False)
    quiet    = args.quiet   or (cfg.quiet   if cfg else False)

    # Fichiers à convertir
    if args.files:
        owl_files = [pathlib.Path(f) for f in args.files]
    elif owl_dir:
        owl_files = sorted(owl_dir.glob("*.owl"))
    else:
        print("Aucun fichier spécifié et aucune config trouvée.")
        return 1

    try:
        results = convert_files(
            owl_files    = owl_files,
            out_dir      = out_dir,
            catalog_path = catalog,
            verbose      = verbose,
            quiet        = quiet,
        )
    except ImportError as exc:
        print(f"[ERREUR] {exc}")
        return 1

    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())