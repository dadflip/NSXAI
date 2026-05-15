"""
NSXAI - Pipeline Neuro-Symbolique Explicable
=============================================
Flux : Ontologie OWL → HermiT (inférences) → KG (NetworkX + CSV) → GNN → Prédictions + Explicabilité

Usage:
    python -m gnn.pipeline --ontology /ontologies/gato.owl --output /output
"""

import argparse
import json
import logging
from pathlib import Path

from gnn.kg_builder import KGBuilder
from gnn.gnn_model import GNNPredictor
from gnn.explainer import OntologyExplainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def run(ontology_path: str, hermit_url: str, output_dir: str):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # ── Étape 1 : Ontologie → KG via HermiT ──────────────────────────────────
    log.info("ÉTAPE 1 — Construction du Knowledge Graph")
    builder = KGBuilder(ontology_path=ontology_path, hermit_url=hermit_url)
    graph, nodes_df, edges_df = builder.build()

    # Sauvegardes KG
    nodes_df.to_csv(output / "nodes.csv", index=False)          # → Neo4j
    edges_df.to_csv(output / "edges.csv", index=False)          # → Neo4j
    import networkx as nx
    nx.write_gexf(graph, str(output / "graph.gexf"))            # → Gephi / NetworkX
    log.info(f"KG : {graph.number_of_nodes()} nœuds, {graph.number_of_edges()} arêtes")

    # ── Étape 2 : GNN — prédictions sur le graphe ─────────────────────────────
    log.info("ÉTAPE 2 — Prédictions GNN")
    predictor = GNNPredictor(graph, nodes_df)
    predictions = predictor.predict()                           # dict {node_id: label, score}
    with open(output / "predictions.json", "w") as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)
    log.info(f"{len(predictions)} prédictions générées")

    # ── Étape 3 : Explicabilité — justification ontologique ───────────────────
    log.info("ÉTAPE 3 — Explicabilité ontologique")
    explainer = OntologyExplainer(hermit_url=hermit_url, graph=graph)
    explanations = explainer.explain(predictions)               # dict {node_id: [raisons]}
    with open(output / "explanations.json", "w") as f:
        json.dump(explanations, f, indent=2, ensure_ascii=False)
    log.info(f"Explications générées → {output}/explanations.json")

    log.info("✓ Pipeline terminé")
    return {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges(),
            "predictions": len(predictions), "output": str(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSXAI Pipeline Neuro-Symbolique")
    parser.add_argument("--ontology", required=True, help="Chemin vers le fichier OWL principal")
    parser.add_argument("--hermit", default="http://hermit:7777", help="URL du service HermiT")
    parser.add_argument("--output", default="/output", help="Répertoire de sortie")
    args = parser.parse_args()
    result = run(args.ontology, args.hermit, args.output)
    print(json.dumps(result, indent=2))
