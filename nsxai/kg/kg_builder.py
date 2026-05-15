"""
kg_builder.py — TTL inférés → Knowledge Graph
==============================================
Charge les fichiers Turtle produits par hermit_infer.py,
construit un DiGraph NetworkX et exporte nodes.csv / edges.csv
(format compatible Neo4j), ainsi que graph.gexf et graph.graphml.

Plus de serveur HermiT REST : les inférences sont déjà dans les TTL.

Utilisable :
  - En ligne de commande (standalone)
  - Importé comme module dans un pipeline

Usage CLI
---------
    python kg_builder.py [OPTIONS] [FILE.ttl ...]

    --config PATH   Config YAML (défaut : ./config.yaml)
    --ttl-dir DIR   Override config.dirs.inferred
    --out DIR       Override config.dirs.kg
    -q / --quiet    Silencieux
    -v / --verbose  Détaillé

Usage module
------------
    from kg_builder import build_kg, KGResult

    result = build_kg(
        ttl_files=["output/inferred/gato.ttl"],
        out_dir="output/kg/",
    )
    print(result.graph.number_of_nodes(), result.nodes_df.shape)
    print(result.gexf_path, result.graphml_path)
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Optional


# ── Types publics ─────────────────────────────────────────────────────────────

@dataclass
class KGResult:
    """Résultat de la construction du KG."""
    graph:        "nx.DiGraph"
    nodes_df:     "pd.DataFrame"
    edges_df:     "pd.DataFrame"
    out_dir:      Optional[pathlib.Path] = None
    success:      bool = False
    error:        Optional[str] = None
    n_nodes:      int = 0
    n_edges:      int = 0
    gexf_path:    Optional[pathlib.Path] = None
    graphml_path: Optional[pathlib.Path] = None


# ── Helpers IRI ───────────────────────────────────────────────────────────────

def _short(iri: str) -> str:
    """Extrait le nom local depuis un IRI (après # ou dernier /)."""
    return iri.split("#")[-1].split("/")[-1]


# ── Chargement des TTL ────────────────────────────────────────────────────────

def _load_graph(ttl_files: list[pathlib.Path], log) -> "rdflib.ConjunctiveGraph":
    """Fusionne tous les TTL dans un unique graphe RDFLib."""
    import rdflib

    g = rdflib.ConjunctiveGraph()
    for ttl in ttl_files:
        log(2, f"  Chargement {ttl.name} ...")
        try:
            g.parse(ttl, format="turtle")
        except Exception as exc:
            log(1, f"  [AVERT] {ttl.name} : {exc}")
    log(1, f"  {len(g)} triplets chargés depuis {len(ttl_files)} fichier(s)")
    return g


# ── Construction du graphe NetworkX ──────────────────────────────────────────

_RDF  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_OWL  = "http://www.w3.org/2002/07/owl#"

_TYPE          = _RDF  + "type"
_SUBCLASSOF    = _RDFS + "subClassOf"
_SUBPROPOF     = _RDFS + "subPropertyOf"
_EQUIV_CLASS   = _OWL  + "equivalentClass"
_SAME_AS       = _OWL  + "sameAs"
_CLASS         = _OWL  + "Class"
_NAMED_IND     = _OWL  + "NamedIndividual"
_OBJECT_PROP   = _OWL  + "ObjectProperty"
_DATATYPE_PROP = _OWL  + "DatatypeProperty"


def _node_type(types: set[str]) -> str:
    if _CLASS         in types: return "class"
    if _NAMED_IND     in types: return "individual"
    if _OBJECT_PROP   in types: return "object_property"
    if _DATATYPE_PROP in types: return "datatype_property"
    return "resource"


def _build_nx(rdf_graph, log) -> tuple["nx.DiGraph", list[dict], list[dict]]:
    """Construit le DiGraph et collecte les lignes nodes/edges."""
    import networkx as nx
    import rdflib

    G          = nx.DiGraph()
    node_rows: list[dict] = []
    edge_rows: list[dict] = []

    # ── Passe 1 : collecter les types de chaque sujet ─────────────────────
    subject_types: dict[str, set[str]] = {}
    for s, p, o in rdf_graph:
        if not isinstance(s, rdflib.URIRef):
            continue
        s_iri = str(s)
        if s_iri not in subject_types:
            subject_types[s_iri] = set()
        if str(p) == _TYPE and isinstance(o, rdflib.URIRef):
            subject_types[s_iri].add(str(o))

    # ── Passe 2 : nœuds ──────────────────────────────────────────────────
    seen_nodes: set[str] = set()

    def _add_node(iri: str) -> str:
        nid = _short(iri)
        if iri not in seen_nodes:
            seen_nodes.add(iri)
            ntype = _node_type(subject_types.get(iri, set()))
            G.add_node(nid, iri=iri, type=ntype)
            node_rows.append({"id": nid, "label": nid, "type": ntype, "iri": iri})
        return nid

    for iri in subject_types:
        _add_node(iri)

    # ── Passe 3 : arêtes (relations objet uniquement) ─────────────────────
    _SKIP_PREDICATES = {_TYPE}          # rdf:type → attribut de nœud, pas d'arête
    _STRUCTURAL      = {                # relations structurelles OWL/RDFS
        _SUBCLASSOF, _SUBPROPOF, _EQUIV_CLASS, _SAME_AS,
    }

    seen_edges: set[tuple[str, str, str]] = set()

    for s, p, o in rdf_graph:
        if not isinstance(s, rdflib.URIRef) or not isinstance(o, rdflib.URIRef):
            continue
        p_iri = str(p)
        if p_iri in _SKIP_PREDICATES:
            continue

        src = _add_node(str(s))
        tgt = _add_node(str(o))
        rel = _short(p_iri)

        key = (src, tgt, rel)
        if key in seen_edges:
            continue
        seen_edges.add(key)

        is_structural = p_iri in _STRUCTURAL
        G.add_edge(src, tgt, relation=rel, structural=is_structural)
        edge_rows.append({
            "source":     src,
            "target":     tgt,
            "relation":   rel,
            "structural": is_structural,
        })

    log(1, f"  Graphe : {G.number_of_nodes()} nœuds, {G.number_of_edges()} arêtes")
    return G, node_rows, edge_rows


# ── Export CSV ────────────────────────────────────────────────────────────────

def _export_csv(
    out_dir: pathlib.Path,
    node_rows: list[dict],
    edge_rows: list[dict],
    log,
) -> tuple[pathlib.Path, pathlib.Path]:
    import pandas as pd

    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_df = pd.DataFrame(node_rows).drop_duplicates(subset="id")
    edges_df = pd.DataFrame(edge_rows).drop_duplicates(subset=["source", "target", "relation"])

    nodes_path = out_dir / "nodes.csv"
    edges_path = out_dir / "edges.csv"
    nodes_df.to_csv(nodes_path, index=False)
    edges_df.to_csv(edges_path, index=False)

    log(1, f"  Exporté → {nodes_path.name} ({len(nodes_df)} lignes)")
    log(1, f"  Exporté → {edges_path.name} ({len(edges_df)} lignes)")
    return nodes_path, edges_path


# ── Export GEXF / GraphML ─────────────────────────────────────────────────────

def _export_graph_formats(
    G: "nx.DiGraph",
    out_dir: pathlib.Path,
    log,
) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Écrit graph.gexf et graph.graphml dans out_dir.

    Notes
    -----
    - GEXF  : format natif Gephi, supporte les métadonnées riches et la
              visualisation dynamique. L'attribut ``structural`` (bool) est
              encodé comme integer (0/1) pour garantir la compatibilité avec
              Gephi 0.9.x qui ne lit pas les booléens GEXF.
    - GraphML : format XML portable (yEd, Cytoscape, igraph…).  Les booléens
                sont sérialisés nativement par NetworkX en ``boolean``.
    """
    import networkx as nx

    out_dir.mkdir(parents=True, exist_ok=True)

    # GEXF — convertir structural bool → int pour compatibilité Gephi
    G_gexf = nx.DiGraph()
    G_gexf.add_nodes_from(
        (n, {**d}) for n, d in G.nodes(data=True)
    )
    G_gexf.add_edges_from(
        (u, v, {**d, "structural": int(d.get("structural", False))})
        for u, v, d in G.edges(data=True)
    )

    gexf_path    = out_dir / "graph.gexf"
    graphml_path = out_dir / "graph.graphml"

    nx.write_gexf(G_gexf, gexf_path)
    log(1, f"  Exporté → {gexf_path.name}")

    nx.write_graphml(G, graphml_path)
    log(1, f"  Exporté → {graphml_path.name}")

    return gexf_path, graphml_path


# Alias rétrocompatible (l'ancienne signature publique s'appelait _export)
def _export(out_dir, node_rows, edge_rows, log):
    return _export_csv(out_dir, node_rows, edge_rows, log)


# ── API publique ──────────────────────────────────────────────────────────────

def build_kg(
    ttl_files: list[str | pathlib.Path],
    out_dir: str | pathlib.Path = "output/kg",
    verbose: bool = False,
    quiet:   bool = False,
) -> KGResult:
    """
    Construit un Knowledge Graph depuis des fichiers TTL inférés.

    Paramètres
    ----------
    ttl_files : chemins vers les .ttl (sortie de hermit_infer)
    out_dir   : dossier de sortie pour nodes.csv / edges.csv /
                graph.gexf / graph.graphml
    verbose   : logs détaillés
    quiet     : supprime tous les logs sauf erreurs

    Retourne
    --------
    KGResult avec graph (NetworkX), nodes_df, edges_df,
    gexf_path et graphml_path.
    Lève ImportError si networkx, rdflib ou pandas sont manquants.
    """
    try:
        import networkx as nx     # noqa: F401
        import rdflib             # noqa: F401
        import pandas as pd       # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"Dépendance manquante : {exc}\n"
            "Installez : pip install networkx rdflib pandas"
        ) from exc

    ttl_paths = [pathlib.Path(f).resolve() for f in ttl_files]
    ttl_paths = [f for f in ttl_paths if f.exists()]
    out_path  = pathlib.Path(out_dir).resolve()

    log_level = 0 if quiet else (2 if verbose else 1)
    def log(level: int, msg: str) -> None:
        if log_level >= level:
            print(msg, flush=True)

    result = KGResult(graph=None, nodes_df=None, edges_df=None)

    if not ttl_paths:
        result.error = "Aucun fichier .ttl valide trouvé."
        log(0, f"[AVERT] {result.error}")
        return result

    log(1, f"\nConstruction du KG depuis {len(ttl_paths)} fichier(s) TTL ...\n")

    try:
        import pandas as pd

        rdf_graph               = _load_graph(ttl_paths, log)
        G, node_rows, edge_rows = _build_nx(rdf_graph, log)
        _export_csv(out_path, node_rows, edge_rows, log)
        gexf_path, graphml_path = _export_graph_formats(G, out_path, log)

        nodes_df = pd.DataFrame(node_rows).drop_duplicates(subset="id")
        edges_df = pd.DataFrame(edge_rows).drop_duplicates(subset=["source", "target", "relation"])

        result.graph        = G
        result.nodes_df     = nodes_df
        result.edges_df     = edges_df
        result.out_dir      = out_path
        result.n_nodes      = G.number_of_nodes()
        result.n_edges      = G.number_of_edges()
        result.gexf_path    = gexf_path
        result.graphml_path = graphml_path
        result.success      = True

        log(1, f"\nTerminé : {result.n_nodes} nœuds, {result.n_edges} arêtes → {out_path}")

    except Exception as exc:
        result.error = str(exc)
        log(0, f"[ERREUR] {exc}")

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kg_builder",
        description="Construit un Knowledge Graph depuis des TTL inférés",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("files", nargs="*", metavar="FILE.ttl",
                   help="Fichiers .ttl explicites (prioritaire sur la config)")
    p.add_argument("--config",  default="config.yaml", metavar="PATH",
                   help="Config YAML (défaut : ./config.yaml)")
    p.add_argument("--ttl-dir", default=None, metavar="DIR",
                   help="Override config.dirs.inferred")
    p.add_argument("--out",     default=None, metavar="DIR",
                   help="Override config.dirs.kg")
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

    # Résolution (args > config > défauts)
    ttl_dir = pathlib.Path(args.ttl_dir).resolve() if args.ttl_dir else (cfg.dirs.inferred if cfg else None)
    out_dir = pathlib.Path(args.out).resolve()     if args.out     else (cfg.dirs.kg       if cfg else pathlib.Path("output/kg").resolve())
    verbose = args.verbose or (cfg.verbose if cfg else False)
    quiet   = args.quiet   or (cfg.quiet   if cfg else False)

    if args.files:
        ttl_files = [pathlib.Path(f) for f in args.files]
    elif ttl_dir and ttl_dir.exists():
        ttl_files = sorted(ttl_dir.glob("*.ttl"))
    else:
        print("Aucun fichier .ttl trouvé. Vérifiez config.dirs.inferred ou passez des FILE.")
        return 1

    try:
        result = build_kg(
            ttl_files = ttl_files,
            out_dir   = out_dir,
            verbose   = verbose,
            quiet     = quiet,
        )
    except ImportError as exc:
        print(f"[ERREUR] {exc}")
        return 1

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())