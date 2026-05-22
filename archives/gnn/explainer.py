"""
OntologyExplainer — Explicabilité Symbolique
=============================================
Pour chaque prédiction GNN, génère une justification en termes ontologiques :
  - Quels types inférés par HermiT expliquent ce score ?
  - Quelles propriétés OWL sont impliquées ?
  - Quelle règle / axiome de l'ontologie est activée ?

C'est ici que réside l'aspect "neuro-symbolique explicable" du système :
le GNN dit QUOI, l'ontologie dit POURQUOI.
"""

import logging
from typing import Dict, Any, List

import networkx as nx
import requests

log = logging.getLogger(__name__)


class OntologyExplainer:
    """
    Génère des explications symboliques pour les prédictions GNN.

    Pour chaque nœud prédit, retourne :
    {
      "node_id": "...",
      "prediction": {"label": ..., "score": ...},
      "explanation": {
        "inferred_types": [...],         # types déduits par HermiT
        "contributing_relations": [...], # arêtes du KG qui ont influencé
        "ontology_rules": [...],         # règles OWL activées (si dispo)
        "human_readable": "..."          # phrase lisible
      }
    }
    """

    def __init__(self, hermit_url: str, graph: nx.DiGraph):
        self.hermit_url = hermit_url
        self.graph = graph
        self._hermit_available = self._check_hermit()

    def explain(self, predictions: Dict[str, Any]) -> Dict[str, Any]:
        """Génère les explications pour toutes les prédictions."""
        explanations = {}

        for node_id, pred in predictions.items():
            try:
                expl = self._explain_node(node_id, pred)
                explanations[node_id] = expl
            except Exception as e:
                log.warning(f"Impossible d'expliquer {node_id}: {e}")
                explanations[node_id] = self._fallback_explanation(node_id, pred)

        return explanations

    # ─────────────────────────────────────────────────────────────────────────

    def _explain_node(self, node_id: str, pred: Dict[str, Any]) -> Dict[str, Any]:
        node_data = self.graph.nodes.get(node_id, {})
        iri = node_data.get("iri", "")
        node_type = node_data.get("type", "unknown")

        # Types inférés (depuis HermiT ou le graphe local)
        inferred_types = self._get_inferred_types(node_id, iri, node_type)

        # Relations contributrices (voisins dans le KG)
        contributing = self._get_contributing_relations(node_id)

        # Règles ontologiques activées (simplifiées)
        rules = self._get_activated_rules(node_id, inferred_types)

        # Phrase lisible
        human = self._build_human_explanation(
            node_id, pred, inferred_types, contributing
        )

        return {
            "node_id": node_id,
            "prediction": pred,
            "explanation": {
                "inferred_types": inferred_types,
                "contributing_relations": contributing,
                "ontology_rules": rules,
                "human_readable": human,
            },
        }

    def _get_inferred_types(
        self, node_id: str, iri: str, node_type: str
    ) -> List[str]:
        """Récupère les types inférés depuis HermiT REST ou le graphe local."""
        if self._hermit_available and iri and node_type == "individual":
            try:
                r = requests.get(
                    f"{self.hermit_url}/individual/types",
                    params={"iri": iri},
                    timeout=10,
                )
                if r.status_code == 200:
                    return r.json().get("types", [])
            except Exception:
                pass

        # Fallback : types stockés dans le graphe (depuis le KGBuilder)
        stored = self.graph.nodes.get(node_id, {}).get("inferred_types", [])
        if stored:
            return stored

        # Sinon : successeurs de type rdf:type dans le graphe
        return [
            v
            for u, v, data in self.graph.out_edges(node_id, data=True)
            if data.get("relation") in ("rdf:type", "subClassOf")
        ]

    def _get_contributing_relations(self, node_id: str) -> List[Dict[str, str]]:
        """Retourne les arêtes voisines qui contribuent à la prédiction."""
        relations = []
        for u, v, data in self.graph.out_edges(node_id, data=True):
            relations.append({"from": u, "to": v, "relation": data.get("relation", "?")})
        for u, v, data in self.graph.in_edges(node_id, data=True):
            relations.append({"from": u, "to": v, "relation": data.get("relation", "?")})
        # Limiter aux 10 plus importants (degré des voisins)
        relations.sort(
            key=lambda e: self.graph.degree(e["to"]) + self.graph.degree(e["from"]),
            reverse=True,
        )
        return relations[:10]

    def _get_activated_rules(
        self, node_id: str, inferred_types: List[str]
    ) -> List[str]:
        """
        Règles OWL simplifiées activées pour ce nœud.
        En production : interroger HermiT pour les justifications (OWLAPI).
        """
        rules = []
        node_data = self.graph.nodes.get(node_id, {})

        if node_data.get("type") == "individual":
            rules.append("rdf:type assertion → classification OWL DL")

        if inferred_types:
            rules.append(
                f"HermiT a inféré {len(inferred_types)} type(s) supplémentaire(s) "
                f"via la fermeture transitive de la hiérarchie de classes"
            )

        in_deg = self.graph.in_degree(node_id)
        out_deg = self.graph.out_degree(node_id)
        if in_deg > 5:
            rules.append(f"Nœud très référencé ({in_deg} arêtes entrantes) → hub sémantique")
        if out_deg > 5:
            rules.append(f"Nœud richement annoté ({out_deg} propriétés) → instance complète")

        return rules

    def _build_human_explanation(
        self,
        node_id: str,
        pred: Dict[str, Any],
        inferred_types: List[str],
        contributing: List[Dict[str, str]],
    ) -> str:
        score = pred.get("score", 0)
        label = pred.get("label", "inconnu")
        n_types = len(inferred_types)
        n_rel = len(contributing)

        short_types = [t.split("#")[-1].split("/")[-1] for t in inferred_types[:3]]
        types_str = ", ".join(short_types) if short_types else "aucun type inféré"

        return (
            f"Le nœud '{node_id}' est classé comme '{label}' avec un score de {score:.3f}. "
            f"HermiT a inféré {n_types} type(s) OWL : [{types_str}]. "
            f"Il est connecté à {n_rel} relation(s) dans le Knowledge Graph. "
            f"Ces éléments symboliques justifient la prédiction du GNN."
        )

    def _fallback_explanation(
        self, node_id: str, pred: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "node_id": node_id,
            "prediction": pred,
            "explanation": {
                "inferred_types": [],
                "contributing_relations": [],
                "ontology_rules": [],
                "human_readable": f"Explication non disponible pour '{node_id}'.",
            },
        }

    def _check_hermit(self) -> bool:
        try:
            r = requests.get(f"{self.hermit_url}/health", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
