#!/usr/bin/env python3
"""
owl2ttl.py  –  Convert OWL/XML ontologies to Turtle (.ttl)
================================================================
Résout automatiquement les imports via catalog-v001.xml (Protégé),
charge les stubs en premier pour éviter les conflits owlready2, puis
sérialise chaque ontologie en Turtle avec des prefixes propres.

Usage
-----
    python3 owl2ttl.py [OPTIONS] [FILE ...]

Options
-------
    --all          Convertit tous les *.owl dans le dossier du script
    --out DIR      Dossier de sortie pour les .ttl  (défaut : ./ttl/)
    --catalog PATH Catalog XML explicite             (défaut : auto-détect)
    -v / --verbose Affiche des informations détaillées
    FILE ...       Un ou plusieurs fichiers .owl à convertir

Exemples
--------
    # Convertir tous les OWL → ./ttl/
    python3 owl2ttl.py --all

    # Fichier unique
    python3 owl2ttl.py its_domain.owl

    # Plusieurs fichiers vers un dossier personnalisé
    python3 owl2ttl.py gado_core.owl gado_full.owl --out /tmp/ttl/

Dépendances
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

# ─────────────────────────────────────────────────────────────────────────────
# Prefixes Turtle à lier dans chaque graphe de sortie
# ─────────────────────────────────────────────────────────────────────────────
PREFIXES: dict[str, str] = {
    "owl":  "http://www.w3.org/2002/07/owl#",
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd":  "http://www.w3.org/2001/XMLSchema#",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    # Suite ontologique GADO/GATO/ITS
    "gc":   "http://surveys.nees.com.br/ontologies/gado_core.owl#",
    "gf":   "http://surveys.nees.com.br/ontologies/gado_full.owl#",
    "gato": "http://surveys.nees.com.br/ontologies/gato.owl#",
    "its":  "http://surveys.nees.com.br/ontologies/its_domain.owl#",
    "itsp": "http://surveys.nees.com.br/ontologies/its/its.pedagogical.owl#",
    # Namespaces MeuTutor (résolus par meututor_stub.owl)
    "mt":   "http://meututor.com.br/Ontologies/MeuTutor.Domain.owl#",
    "mtcp": "http://meututor.com.br/Ontologies/MeuTutor.Domain.CP.owl#",
    "mtcu": "http://meututor.com.br/Ontologies/MeuTutor.Domain.Curriculum.owl#",
    "mtr":  "http://meututor.com.br/Ontologies/MeuTutor.Domain.Resource.owl#",
    # Vocabulaires externes (résolus par stubs)
    "sioc": "http://rdfs.org/sioc/ns#",
    "inst": "http://nsxai.org/instances#",
}

# Stubs à pré-charger AVANT toute autre ontologie (évite conflits owlready2)
STUB_FILENAMES = ["meututor_stub.owl", "sioc_stub.owl"]


# ─────────────────────────────────────────────────────────────────────────────
# Lecture du catalog-v001.xml
# ─────────────────────────────────────────────────────────────────────────────

def load_catalog(catalog_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Parse un catalog-v001.xml Protégé → {IRI → chemin absolu local}."""
    catalog_ns = {"c": "urn:oasis:names:tc:entity:xmlns:xml:catalog"}
    tree = ET.parse(catalog_path)
    root = tree.getroot()
    base = catalog_path.parent
    mapping: dict[str, pathlib.Path] = {}
    for uri_el in root.findall(".//c:uri", catalog_ns):
        iri   = uri_el.get("name", "").rstrip("/")
        local = uri_el.get("uri", "")
        if iri and local:
            abs_path = (base / local).resolve()
            mapping[iri]       = abs_path   # sans slash final
            mapping[iri + "/"] = abs_path   # avec slash (owlready2 en ajoute parfois)
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# Patch owlready2 : rediriger les téléchargements HTTP vers les fichiers locaux
# ─────────────────────────────────────────────────────────────────────────────

def install_catalog_opener(catalog: dict[str, pathlib.Path]) -> None:
    """
    Remplace urllib.request.urlopen dans le module owlready2.namespace par une
    version qui intercepte les IRI catalog-mappées et renvoie le fichier local.
    Les IRI non reconnues passent par l'opener original (réseau réel).

    POURQUOI : owlready2 ne lit pas catalog-v001.xml lui-même. Quand il rencontre
    un <Import> http://..., il appelle directement urllib.request.urlopen.
    Ce patch court-circuite cet appel réseau pour les IRI locales.
    """
    try:
        import owlready2.namespace as _ns_mod
    except ImportError:
        return

    _original_urlopen = urllib.request.urlopen

    def _catalog_urlopen(url_or_req, *args, **kwargs):
        url = url_or_req if isinstance(url_or_req, str) else url_or_req.full_url
        iri = url.rstrip("/")
        if iri in catalog:
            data = catalog[iri].read_bytes()
            return urllib.response.addinfourl(io.BytesIO(data), {}, url, 200)
        return _original_urlopen(url_or_req, *args, **kwargs)

    # owlready2.namespace garde sa propre référence à urllib.request
    _ns_mod.urllib.request.urlopen = _catalog_urlopen  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# Conversion d'un fichier OWL → TTL
# ─────────────────────────────────────────────────────────────────────────────

def convert_owl_to_ttl(
    world,
    owl_file: pathlib.Path,
    out_dir: pathlib.Path,
    verbose: bool = False,
) -> bool:
    """
    Charge *owl_file* dans le *world* partagé (stubs déjà présents),
    exporte en N-Triples, re-parse avec rdflib et sérialise en Turtle.
    Retourne True en cas de succès.
    """
    import rdflib

    if verbose:
        print(f"  Chargement {owl_file.name} …", end="", flush=True)

    onto = None
    try:
        onto = world.get_ontology(owl_file.as_uri()).load()
    except Exception as exc:
        print(f"\n  [AVERT]  {owl_file.name} : {exc}", file=sys.stderr)
        # Tente de récupérer une ontologie partiellement chargée dans le world
        onto = world.ontologies.get(owl_file.as_uri())

    if onto is None:
        print(f"  [ÉCHEC]  Impossible de charger {owl_file.name}", file=sys.stderr)
        return False

    # Export interne owlready2 → N-Triples
    buf = io.BytesIO()
    try:
        onto.graph.save(buf, format="ntriples")
    except Exception as exc:
        print(f"  [ÉCHEC]  Sérialisation {owl_file.name} : {exc}", file=sys.stderr)
        return False

    nt_bytes = buf.getvalue()
    if not nt_bytes.strip():
        print(f"  [AVERT]  {owl_file.name} : aucun triplet — ignoré.", file=sys.stderr)
        return False

    # rdflib : N-Triples → Turtle
    g = rdflib.Graph()
    g.parse(data=nt_bytes, format="ntriples")
    for prefix, uri in PREFIXES.items():
        g.bind(prefix, rdflib.Namespace(uri))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{owl_file.stem}.ttl"
    out_path.write_text(g.serialize(format="turtle"), encoding="utf-8")

    n = len(g)
    if verbose:
        print(f" {n} triplets → {out_path}")
    else:
        print(f"  {owl_file.name:38s}  {n:>6} triplets  →  ttl/{out_path.name}")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convertit les ontologies OWL/XML en Turtle (.ttl)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="*", metavar="FILE",
                   help="Fichiers .owl à convertir")
    p.add_argument("--all", action="store_true",
                   help="Convertir tous les *.owl dans le dossier du script")
    p.add_argument("--out", default=None, metavar="DIR",
                   help="Dossier de sortie (défaut : ./ttl/)")
    p.add_argument("--catalog", default=None, metavar="PATH",
                   help="Chemin vers catalog-v001.xml (défaut : auto-détect)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Informations détaillées")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        import owlready2
        import rdflib  # noqa: F401
    except ImportError as exc:
        print(f"[ERREUR] Dépendance manquante : {exc}")
        print("         Installez : pip install owlready2 rdflib")
        return 1

    script_dir = pathlib.Path(__file__).parent.resolve()

    # ── Fichiers à convertir ─────────────────────────────────────────────────
    if args.all:
        owl_files = sorted(script_dir.glob("*.owl"))
    elif args.files:
        owl_files = [pathlib.Path(f).resolve() for f in args.files]
    else:
        print("Aucun fichier spécifié. Utilisez --all ou passez des FILE.")
        print("Lancez avec --help pour l'aide.")
        return 1

    owl_files = [f for f in owl_files if f.exists()]
    if not owl_files:
        print("Aucun fichier .owl trouvé.")
        return 1

    # ── Catalog ──────────────────────────────────────────────────────────────
    catalog_path = (
        pathlib.Path(args.catalog).resolve()
        if args.catalog
        else (script_dir / "catalog-v001.xml")
    )
    catalog: dict[str, pathlib.Path] = {}
    if catalog_path.exists():
        catalog = load_catalog(catalog_path)
        print(f"Catalog chargé : {catalog_path.name}  ({len(catalog) // 2} entrées)")
    else:
        print(f"[AVERT] catalog-v001.xml introuvable dans {script_dir}", file=sys.stderr)

    # ── Patch : résolution HTTP → fichiers locaux ─────────────────────────────
    # DOIT être appelé avant tout import/load owlready2
    install_catalog_opener(catalog)

    # ── Monde owlready2 partagé + pré-chargement des stubs ───────────────────
    # Les stubs doivent être dans le world AVANT les ontologies qui les importent.
    # Sans ça owlready2 lève "_check_update property is not defined" sur les
    # propriétés redéfinies (ex: mtcu:difficulty déclaré ObjectProperty puis DataProperty).
    world = owlready2.World()
    owlready2.onto_path.insert(0, str(script_dir))

    print("Pré-chargement des stubs …")
    for stub_name in STUB_FILENAMES:
        stub_path = script_dir / stub_name
        if stub_path.exists():
            try:
                world.get_ontology(stub_path.as_uri()).load()
                print(f"  stub OK : {stub_name}")
            except Exception as exc:
                print(f"  stub AVERT ({stub_name}) : {exc}", file=sys.stderr)
        else:
            print(f"  stub ABSENT : {stub_name} (ignoré)", file=sys.stderr)

    # ── Conversion ───────────────────────────────────────────────────────────
    print(f"\nConversion de {len(owl_files)} fichier(s) …\n")
    ok = fail = 0
    for owl_file in owl_files:
        out_dir = (
            pathlib.Path(args.out).resolve()
            if args.out
            else (owl_file.parent / "ttl")
        )
        if convert_owl_to_ttl(world, owl_file, out_dir, verbose=args.verbose):
            ok += 1
        else:
            fail += 1

    print(f"\nTerminé : {ok} converti(s), {fail} échec(s).")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
