"""
KGBuilder — Ontologie OWL → Knowledge Graph
============================================
1. Charge l'ontologie avec owlready2
2. Lance HermiT pour obtenir les inférences (via l'API REST ou owlready2)
3. Construit un graphe NetworkX + DataFrames nodes/edges (prêts pour Neo4j)
"""

import logging
from typing import Tuple

import networkx as nx
import pandas as pd
import requests
from owlready2 import get_ontology, sync_reasoner_hermit

log = logging.getLogger(__name__)


class KGBuilder:
    """
    Construit un Knowledge Graph depuis une ontologie OWL.

    Stratégie d'inférence (dans l'ordre de priorité) :
      1. Service HermiT REST (si disponible à hermit_url)
      2. owlready2 + HermiT en local (fallback, nécessite Java)
    """

    def __init__(self, ontology_path: str, hermit_url: str = "http://hermit:7777"):
        self.ontology_path = str(ontology_path)
        self.hermit_url = hermit_url
        self.onto = None

    # ─────────────────────────────────────────────────────────────────────────
    # Interface publique
    # ─────────────────────────────────────────────────────────────────────────

    def build(self) -> Tuple[nx.DiGraph, pd.DataFrame, pd.DataFrame]:
        """
        Retourne (graph, nodes_df, edges_df).
        nodes_df et edges_df sont au format CSV-Neo4j (colonnes :ID, :LABEL, etc.)
        """
        self._load_ontology()
        inferred = self._run_inference()
        graph, nodes_df, edges_df = self._build_graph(inferred)
        return graph, nodes_df, edges_df

    # ─────────────────────────────────────────────────────────────────────────
    # Étapes internes
    # ─────────────────────────────────────────────────────────────────────────

    def _load_ontology(self):
        log.info(f"Chargement de l'ontologie : {self.ontology_path}")
        self.onto = get_ontology(f"file://{self.ontology_path}").load()
        log.info(f"  Classes    : {len(list(self.onto.classes()))}")
        log.info(f"  Individus  : {len(list(self.onto.individuals()))}")

    def _run_inference(self) -> dict:
        """
        Lance HermiT et retourne un dict d'inférences :
        {
          "class_hierarchy": {class_iri: [subclass_iri, ...]},
          "individual_types": {ind_iri: [type_iri, ...]},
          "individual_properties": {ind_iri: {prop_iri: [values]}},
        }
        """
        # Essai 1 : service REST HermiT
        if self._hermit_service_available():
            log.info("Inférence via le service HermiT REST")
            return self._infer_via_rest()

        # Essai 2 : owlready2 + HermiT local
        log.info("Inférence via owlready2 + HermiT local (fallback)")
        return self._infer_via_owlready2()

    def _hermit_service_available(self) -> bool:
        try:
            r = requests.get(f"{self.hermit_url}/health", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _infer_via_rest(self) -> dict:
        """Interroge le service HermiT REST pour les inférences."""
        inferred = {"class_hierarchy": {}, "individual_types": {}, "individual_properties": {}}

        # Hiérarchie de classes
        classes_resp = requests.get(f"{self.hermit_url}/classes", timeout=30).json()
        for cls_iri in classes_resp.get("classes", []):
            sub_resp = requests.get(
                f"{self.hermit_url}/classes/subclasses",
                params={"iri": cls_iri, "direct": "true"},
                timeout=30,
            ).json()
            inferred["class_hierarchy"][cls_iri] = sub_resp.get("subclasses", [])

        # Types des individus
        ind_resp = requests.get(f"{self.hermit_url}/instances", timeout=60).json()
        for ind_iri in ind_resp.get("instances", []):
            types_resp = requests.get(
                f"{self.hermit_url}/individual/types",
                params={"iri": ind_iri},
                timeout=30,
            ).json()
            inferred["individual_types"][ind_iri] = types_resp.get("types", [])

            props_resp = requests.get(
                f"{self.hermit_url}/individual/properties",
                params={"iri": ind_iri},
                timeout=30,
            ).json()
            inferred["individual_properties"][ind_iri] = props_resp.get("properties", {})

        return inferred

    def _infer_via_owlready2(self) -> dict:
        """Utilise owlready2 pour lancer HermiT en local."""
        sync_reasoner_hermit(self.onto, infer_property_values=True)

        inferred = {"class_hierarchy": {}, "individual_types": {}, "individual_properties": {}}

        # Hiérarchie
        for cls in self.onto.classes():
            inferred["class_hierarchy"][cls.iri] = [
                sub.iri for sub in cls.subclasses()
            ]

        # Types inférés des individus
        for ind in self.onto.individuals():
            inferred["individual_types"][ind.iri] = [
                t.iri for t in ind.INDIRECT_is_a if hasattr(t, "iri")
            ]
            props = {}
            for prop in ind.get_properties():
                values = list(prop[ind])
                if values:
                    props[prop.iri] = [
                        v.iri if hasattr(v, "iri") else str(v) for v in values
                    ]
            inferred["individual_properties"][ind.iri] = props

        return inferred

    # ─────────────────────────────────────────────────────────────────────────
    # Construction du graphe
    # ─────────────────────────────────────────────────────────────────────────

    def _build_graph(
        self, inferred: dict
    ) -> Tuple[nx.DiGraph, pd.DataFrame, pd.DataFrame]:
        """
        Crée :
        - Un DiGraph NetworkX (pour le GNN)
        - nodes.csv   → colonnes : id, label, type, iri
        - edges.csv   → colonnes : source, target, relation
        """
        G = nx.DiGraph()
        node_rows = []
        edge_rows = []

        def _short(iri: str) -> str:
            """Nom court depuis un IRI."""
            return iri.split("#")[-1].split("/")[-1]

        # ── Nœuds : classes ──────────────────────────────────────────────────
        for cls_iri, subs in inferred["class_hierarchy"].items():
            nid = _short(cls_iri)
            G.add_node(nid, iri=cls_iri, type="class")
            node_rows.append({"id": nid, "label": nid, "type": "class", "iri": cls_iri})
            for sub_iri in subs:
                sub_id = _short(sub_iri)
                G.add_node(sub_id, iri=sub_iri, type="class")
                G.add_edge(sub_id, nid, relation="subClassOf")
                edge_rows.append({"source": sub_id, "target": nid, "relation": "subClassOf"})

        # ── Nœuds : individus ────────────────────────────────────────────────
        for ind_iri, types in inferred["individual_types"].items():
            nid = _short(ind_iri)
            G.add_node(nid, iri=ind_iri, type="individual", inferred_types=types)
            node_rows.append({"id": nid, "label": nid, "type": "individual", "iri": ind_iri})
            # Arêtes rdf:type vers les types inférés
            for t_iri in types:
                t_id = _short(t_iri)
                if G.has_node(t_id):
                    G.add_edge(nid, t_id, relation="rdf:type")
                    edge_rows.append({"source": nid, "target": t_id, "relation": "rdf:type"})

        # ── Arêtes : propriétés des individus ────────────────────────────────
        for ind_iri, props in inferred["individual_properties"].items():
            src = _short(ind_iri)
            for prop_iri, values in props.items():
                rel = _short(prop_iri)
                for val_iri in values:
                    tgt = _short(val_iri)
                    if G.has_node(tgt):
                        G.add_edge(src, tgt, relation=rel)
                        edge_rows.append({"source": src, "target": tgt, "relation": rel})

        nodes_df = pd.DataFrame(node_rows).drop_duplicates(subset="id")
        edges_df = pd.DataFrame(edge_rows).drop_duplicates()

        log.info(f"Graphe construit : {G.number_of_nodes()} nœuds, {G.number_of_edges()} arêtes")
        return G, nodes_df, edges_df
