#!/usr/bin/env python3
"""
owl2ttl.py  -  Convert OWL/XML ontologies to Turtle (.ttl)
================================================================
Resout automatiquement les imports via catalog-v001.xml (Protege),
detecte et pre-charge les stubs depuis le catalog, extrait les prefixes
directement depuis les fichiers OWL source (aucun namespace hardcode),
puis serialise chaque ontologie en Turtle avec des prefixes propres.

Le script est entierement agnostique : il ne connait aucune ontologie
specifique et fonctionne avec n'importe quelle suite OWL.

Usage
-----
    python3 owl2ttl.py [OPTIONS] [FILE ...]

Options
-------
    --all          Convertit tous les *.owl dans le dossier du script
    --out DIR      Dossier de sortie pour les .ttl  (defaut : ./ttl/)
    --catalog PATH Catalog XML explicite             (defaut : auto-detect)
    -v / --verbose Affiche des informations detaillees
    FILE ...       Un ou plusieurs fichiers .owl a convertir

Exemples
--------
    python3 owl2ttl.py --all
    python3 owl2ttl.py its_domain.owl
    python3 owl2ttl.py gado_core.owl gado_full.owl --out /tmp/ttl/

Dependances
-----------
    pip install owlready2 rdflib
"""

import argparse
import io
import pathlib
import sys
import urllib.request
import urllib.response
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Prefixes standards (W3C universels) — toujours lies dans la sortie Turtle.
# Les prefixes specifiques aux ontologies sont extraits dynamiquement.
# ---------------------------------------------------------------------------
STANDARD_PREFIXES: dict[str, str] = {
    "owl":  "http://www.w3.org/2002/07/owl#",
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}


# ---------------------------------------------------------------------------
# Extraction dynamique des prefixes depuis les fichiers OWL
# ---------------------------------------------------------------------------

def extract_prefixes_from_owl(owl_files: list[pathlib.Path]) -> dict[str, str]:
    """
    Parse les declarations <Prefix name="..." IRI="..."/> dans les fichiers OWL
    et retourne un dict {nom_prefix -> IRI} fusionne sur tous les fichiers.
    Les prefixes vides (name="") et les standards W3C sont ignores.
    """
    prefixes: dict[str, str] = {}
    skip = {"owl", "rdf", "rdfs", "xsd", "xml"}
    for owl_file in owl_files:
        try:
            tree = ET.parse(owl_file)
            root = tree.getroot()
            for elem in root.iter():
                local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if local == "Prefix":
                    name = elem.get("name") or ""
                    iri  = elem.get("IRI", "")
                    if name and iri and name not in skip:
                        prefixes[name] = iri
        except ET.ParseError:
            pass
    return prefixes


# ---------------------------------------------------------------------------
# Lecture du catalog-v001.xml
# ---------------------------------------------------------------------------

def load_catalog(catalog_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Parse un catalog-v001.xml Protege -> {IRI -> chemin absolu local}."""
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
            mapping[iri]       = abs_path
            mapping[iri + "/"] = abs_path
    return mapping


# ---------------------------------------------------------------------------
# Detection automatique des stubs depuis le catalog
# ---------------------------------------------------------------------------

def detect_stubs(
    catalog: dict[str, pathlib.Path],
    owl_files_to_convert: list[pathlib.Path],
) -> list[pathlib.Path]:
    """
    Identifie les fichiers stub a pre-charger dans le world owlready2.

    Un stub est un fichier .owl present dans le catalog dont le chemin
    physique N'EST PAS dans la liste des fichiers a convertir.
    Cela couvre tous les vocabulaires externes (sioc_stub.owl, foaf_stub.owl,
    etc.) quelle que soit leur IRI, sans aucun nom hardcode.
    """
    convert_paths: set[pathlib.Path] = {f.resolve() for f in owl_files_to_convert}
    stubs: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for fpath in catalog.values():
        r = fpath.resolve()
        if r in convert_paths:
            continue   # ontologie locale a convertir -> pas un stub
        if not fpath.exists():
            continue
        if r in seen:
            continue
        seen.add(r)
        stubs.append(fpath)
    return stubs


# ---------------------------------------------------------------------------
# Patch owlready2 : rediriger HTTP -> fichiers locaux via le catalog
# ---------------------------------------------------------------------------

def install_catalog_opener(catalog: dict[str, pathlib.Path]) -> None:
    """
    Remplace urllib.request.urlopen dans owlready2.namespace par une version
    qui intercepte les IRI catalog-mappees et renvoie le fichier local.
    Les IRI non reconnues passent par l'opener original (reseau reel).
    """
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


# ---------------------------------------------------------------------------
# Recuperation de l'ontologie dans le world apres un echec de chargement
# ---------------------------------------------------------------------------

def _find_onto_in_world(world, owl_file: pathlib.Path):
    """
    owlready2 peut lever une exception tout en ayant quand meme charge
    (partiellement) l'ontologie dans le world sous deux URI possibles :
    - l'URI fichier  : file:///chemin/vers/fichier.owl#
    - l'IRI canonique : http://...owl#  (xml:base du fichier)
    Cette fonction les cherche toutes les deux.
    """
    # 1. URI fichier (avec et sans fragment #)
    file_uri = owl_file.as_uri()
    for candidate in (file_uri, file_uri + "#", file_uri.rstrip("/") + "#"):
        onto = world.ontologies.get(candidate)
        if onto is not None:
            return onto

    # 2. IRI canonique extraite du xml:base du fichier OWL
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


# ---------------------------------------------------------------------------
# Conversion d'un fichier OWL -> TTL
# ---------------------------------------------------------------------------

def convert_owl_to_ttl(
    world,
    owl_file: pathlib.Path,
    out_dir: pathlib.Path,
    extra_prefixes: dict[str, str],
    verbose: bool = False,
) -> bool:
    """
    Charge *owl_file* dans le *world* partage (stubs deja presents),
    exporte en N-Triples, re-parse avec rdflib et serialise en Turtle.
    Retourne True en cas de succes.
    """
    import rdflib

    if verbose:
        print(f"  Chargement {owl_file.name} ...", end="", flush=True)

    onto = None
    try:
        onto = world.get_ontology(owl_file.as_uri()).load()
    except Exception as exc:
        print(f"\n  [AVERT]  {owl_file.name} : {exc}", file=sys.stderr)
        # owlready2 peut avoir quand meme charge l'ontologie malgre l'exception
        onto = _find_onto_in_world(world, owl_file)

    if onto is None:
        print(f"  [ECHEC]  Impossible de charger {owl_file.name}", file=sys.stderr)
        return False

    buf = io.BytesIO()
    try:
        onto.graph.save(buf, format="ntriples")
    except Exception as exc:
        print(f"  [ECHEC]  Serialisation {owl_file.name} : {exc}", file=sys.stderr)
        return False

    nt_bytes = buf.getvalue()
    if not nt_bytes.strip():
        print(f"  [AVERT]  {owl_file.name} : aucun triplet — ignore.", file=sys.stderr)
        return False

    g = rdflib.Graph()
    g.parse(data=nt_bytes, format="ntriples")

    all_prefixes = {**STANDARD_PREFIXES, **extra_prefixes}
    for prefix, uri in all_prefixes.items():
        g.bind(prefix, rdflib.Namespace(uri))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{owl_file.stem}.ttl"
    out_path.write_text(g.serialize(format="turtle"), encoding="utf-8")

    n = len(g)
    if verbose:
        print(f" {n} triplets -> {out_path}")
    else:
        print(f"  {owl_file.name:38s}  {n:>6} triplets  ->  ttl/{out_path.name}")

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convertit les ontologies OWL/XML en Turtle (.ttl)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", metavar="FILE",
                   help="Fichiers .owl a convertir")
    p.add_argument("--all", action="store_true",
                   help="Convertir tous les *.owl dans le dossier du script")
    p.add_argument("--out", default=None, metavar="DIR",
                   help="Dossier de sortie (defaut : ./ttl/)")
    p.add_argument("--catalog", default=None, metavar="PATH",
                   help="Chemin vers catalog-v001.xml (defaut : auto-detect)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Informations detaillees")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        import owlready2
        import rdflib  # noqa: F401
    except ImportError as exc:
        print(f"[ERREUR] Dependance manquante : {exc}")
        print("         Installez : pip install owlready2 rdflib")
        return 1

    script_dir = pathlib.Path(__file__).parent.resolve()

    # -- Fichiers a convertir ------------------------------------------------
    if args.all:
        owl_files = sorted(script_dir.glob("*.owl"))
    elif args.files:
        owl_files = [pathlib.Path(f).resolve() for f in args.files]
    else:
        print("Aucun fichier specifie. Utilisez --all ou passez des FILE.")
        print("Lancez avec --help pour l'aide.")
        return 1

    owl_files = [f for f in owl_files if f.exists()]
    if not owl_files:
        print("Aucun fichier .owl trouve.")
        return 1

    # -- Catalog -------------------------------------------------------------
    catalog_path = (
        pathlib.Path(args.catalog).resolve()
        if args.catalog
        else (script_dir / "catalog-v001.xml")
    )
    catalog: dict[str, pathlib.Path] = {}
    if catalog_path.exists():
        catalog = load_catalog(catalog_path)
        print(f"Catalog charge : {catalog_path.name}  ({len(catalog) // 2} entrees)")
    else:
        print(f"[AVERT] catalog-v001.xml introuvable dans {script_dir}", file=sys.stderr)

    # -- Patch HTTP -> local (avant tout chargement owlready2) ---------------
    install_catalog_opener(catalog)

    # -- Extraction dynamique des prefixes ------------------------------------
    extra_prefixes = extract_prefixes_from_owl(owl_files)
    if args.verbose and extra_prefixes:
        print(f"Prefixes extraits ({len(extra_prefixes)}) : "
              + ", ".join(f"{k}:" for k in sorted(extra_prefixes)))

    # -- Detection et pre-chargement des stubs --------------------------------
    # Un stub = fichier catalog non present dans la liste a convertir.
    # Il doit etre charge EN PREMIER dans le world pour eviter les conflits
    # owlready2 sur les proprietes redefines dans les ontologies importatrices.
    stub_files = detect_stubs(catalog, owl_files)

    world = owlready2.World()
    owlready2.onto_path.insert(0, str(script_dir))

    if stub_files:
        print("Pre-chargement des stubs ...")
        for stub_path in stub_files:
            try:
                world.get_ontology(stub_path.as_uri()).load()
                print(f"  stub OK : {stub_path.name}")
            except Exception as exc:
                print(f"  stub AVERT ({stub_path.name}) : {exc}", file=sys.stderr)
    elif args.verbose:
        print("Aucun stub externe detecte dans le catalog.")

    # -- Conversion ----------------------------------------------------------
    print(f"\nConversion de {len(owl_files)} fichier(s) ...\n")
    ok = fail = 0
    for owl_file in owl_files:
        out_dir = (
            pathlib.Path(args.out).resolve()
            if args.out
            else (owl_file.parent / "ttl")
        )
        if convert_owl_to_ttl(world, owl_file, out_dir, extra_prefixes,
                               verbose=args.verbose):
            ok += 1
        else:
            fail += 1

    print(f"\nTermine : {ok} converti(s), {fail} echec(s).")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())