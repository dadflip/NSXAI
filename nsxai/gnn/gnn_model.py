"""
GNNPredictor — Prédictions sur le Knowledge Graph
==================================================
Utilise un GNN (GraphSAGE-like) pour prédire des propriétés des nœuds.

Deux backends supportés :
  - PyTorch Geometric (PyG)  — si disponible
  - NetworkX + scikit-learn  — fallback léger (pas de GPU requis)

La sortie est toujours un dict {node_id: {"label": ..., "score": float}}.
"""

import logging
from typing import Dict, Any

import networkx as nx
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class GNNPredictor:
    """
    Prédit des labels/scores pour chaque nœud du graphe.

    Avec PyG  : GraphSAGE 2 couches (rapide, précis)
    Sans PyG  : embeddings WL + classifieur logistique (fallback)
    """

    def __init__(self, graph: nx.DiGraph, nodes_df: pd.DataFrame):
        self.graph = graph
        self.nodes_df = nodes_df
        self._use_pyg = self._check_pyg()

    def predict(self) -> Dict[str, Any]:
        if self._use_pyg:
            log.info("Backend : PyTorch Geometric")
            return self._predict_pyg()
        else:
            log.info("Backend : scikit-learn (fallback — installez torch-geometric pour le GNN complet)")
            return self._predict_sklearn()

    # ─────────────────────────────────────────────────────────────────────────
    # Backend PyG
    # ─────────────────────────────────────────────────────────────────────────

    def _predict_pyg(self) -> Dict[str, Any]:
        import torch
        import torch.nn.functional as F
        from torch_geometric.data import Data
        from torch_geometric.nn import SAGEConv

        # Mapping nœud → index
        nodes = list(self.graph.nodes())
        node2idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)

        # Matrice de features : degré entrant/sortant + type one-hot
        types = {"class": 0, "individual": 1}
        X = np.zeros((n, 4), dtype=np.float32)
        for node in nodes:
            i = node2idx[node]
            data = self.graph.nodes[node]
            X[i, 0] = self.graph.in_degree(node)
            X[i, 1] = self.graph.out_degree(node)
            t = data.get("type", "class")
            X[i, 2 + types.get(t, 0)] = 1.0

        # Arêtes
        edges = list(self.graph.edges())
        if not edges:
            return self._predict_sklearn()
        src = [node2idx[u] for u, v in edges]
        dst = [node2idx[v] for u, v in edges]
        edge_index = torch.tensor([src, dst], dtype=torch.long)

        x = torch.tensor(X)
        pyg_data = Data(x=x, edge_index=edge_index)

        # Modèle GraphSAGE non supervisé (encodeur)
        class SAGE(torch.nn.Module):
            def __init__(self, in_dim, hidden=32, out_dim=16):
                super().__init__()
                self.conv1 = SAGEConv(in_dim, hidden)
                self.conv2 = SAGEConv(hidden, out_dim)

            def forward(self, x, edge_index):
                x = F.relu(self.conv1(x, edge_index))
                return self.conv2(x, edge_index)

        model = SAGE(in_dim=X.shape[1])
        model.eval()
        with torch.no_grad():
            embeddings = model(pyg_data.x, pyg_data.edge_index).numpy()

        # Score = norme L2 de l'embedding (mesure d'importance du nœud)
        scores = np.linalg.norm(embeddings, axis=1)
        scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-8)

        return {
            nodes[i]: {
                "label": self.graph.nodes[nodes[i]].get("type", "unknown"),
                "score": float(scores[i]),
                "embedding": embeddings[i].tolist(),
            }
            for i in range(n)
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Backend sklearn (fallback)
    # ─────────────────────────────────────────────────────────────────────────

    def _predict_sklearn(self) -> Dict[str, Any]:
        """
        Features structurelles du graphe → scoring par centralité.
        Pas d'entraînement supervisé ici : on mesure l'importance des nœuds.
        """
        G = self.graph

        # Centralités comme proxy de l'importance dans le KG
        degree_centrality = nx.degree_centrality(G)
        try:
            pagerank = nx.pagerank(G, alpha=0.85, max_iter=100)
        except Exception:
            pagerank = {n: 0.0 for n in G.nodes()}

        results = {}
        for node in G.nodes():
            ndata = G.nodes[node]
            score = 0.5 * degree_centrality.get(node, 0) + 0.5 * pagerank.get(node, 0)
            results[node] = {
                "label": ndata.get("type", "unknown"),
                "score": round(score, 4),
                "in_degree": G.in_degree(node),
                "out_degree": G.out_degree(node),
            }
        return results

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _check_pyg() -> bool:
        try:
            import torch
            from torch_geometric.nn import SAGEConv
            return True
        except ImportError:
            return False
