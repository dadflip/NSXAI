"""
GNNPredictor — Prédictions sur le Knowledge Graph
==================================================
Utilise un GNN (GraphSAGE-like) pour prédire des propriétés des nœuds.

Deux backends supportés :
  - PyTorch Geometric (PyG)
  - NetworkX + scikit-learn (fallback)

Sortie :
    {node_id: {"label": ..., "score": float}}
"""

import logging
from typing import Dict, Any

import networkx as nx
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class GNNPredictor:
    """
    Ce modèle transforme un graphe en trois niveaux de représentation :

    1. Features initiales (vecteurs d’entrée)
    2. Embeddings GNN (vecteurs appris)
    3. Score final (réduction du vecteur en scalaire)
    """

    def __init__(self, graph: nx.DiGraph, nodes_df: pd.DataFrame):
        self.graph = graph
        self.nodes_df = nodes_df

        # Détection du backend GNN disponible
        self._use_pyg = self._check_pyg()

    def predict(self) -> Dict[str, Any]:
        """
        Choisit le backend d’exécution.
        """
        if self._use_pyg:
            log.info("Backend : PyTorch Geometric (GNN)")
            return self._predict_pyg()
        else:
            log.info("Backend : NetworkX fallback")
            return self._predict_sklearn()

    # ============================================================
    # Backend PyTorch Geometric (GNN réel)
    # ============================================================

    def _predict_pyg(self) -> Dict[str, Any]:
        import torch
        import torch.nn.functional as F
        from torch_geometric.data import Data
        from torch_geometric.nn import SAGEConv

        # --------------------------------------------------------
        # 1. Indexation des nœuds
        # --------------------------------------------------------
        # On convertit les identifiants de nœuds en indices numériques
        nodes = list(self.graph.nodes())
        node2idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)

        # --------------------------------------------------------
        # 2. Construction des vecteurs d’entrée (X)
        # --------------------------------------------------------
        # X est la matrice de features des nœuds.
        #
        # Chaque ligne i correspond au vecteur du nœud i :
        #
        # X[i] = [
        #   degré entrant,
        #   degré sortant,
        #   type_class (one-hot),
        #   type_individual (one-hot)
        # ]
        #
        # C’est la première représentation vectorielle du graphe.
        # --------------------------------------------------------
        types = {"class": 0, "individual": 1}
        X = np.zeros((n, 4), dtype=np.float32)

        for node in nodes:
            i = node2idx[node]
            data = self.graph.nodes[node]

            # composantes structurelles du graphe
            X[i, 0] = self.graph.in_degree(node)
            X[i, 1] = self.graph.out_degree(node)

            # encodage du type du nœud
            t = data.get("type", "class")
            X[i, 2 + types.get(t, 0)] = 1.0

        # --------------------------------------------------------
        # 3. Construction des arêtes (edge_index)
        # --------------------------------------------------------
        # Format PyG : matrice [2, nombre_d_arêtes]
        edges = list(self.graph.edges())
        if not edges:
            return self._predict_sklearn()

        src = [node2idx[u] for u, v in edges]
        dst = [node2idx[v] for u, v in edges]

        edge_index = torch.tensor([src, dst], dtype=torch.long)

        pyg_data = Data(
            x=torch.tensor(X),
            edge_index=edge_index
        )

        # --------------------------------------------------------
        # 4. Modèle GraphSAGE
        # --------------------------------------------------------
        class SAGE(torch.nn.Module):
            def __init__(self, in_dim, hidden=32, out_dim=16):
                super().__init__()

                # première agrégation des voisins
                self.conv1 = SAGEConv(in_dim, hidden)

                # projection finale
                self.conv2 = SAGEConv(hidden, out_dim)

            def forward(self, x, edge_index):
                x = F.relu(self.conv1(x, edge_index))
                return self.conv2(x, edge_index)

        model = SAGE(in_dim=X.shape[1])
        model.eval()

        # --------------------------------------------------------
        # 5. Embeddings (vecteurs appris par le GNN)
        # --------------------------------------------------------
        # embeddings[i] est le vecteur final du nœud i
        # Il encode :
        # - structure du graphe
        # - voisinage
        # - type de nœud
        # --------------------------------------------------------
        with torch.no_grad():
            embeddings = model(pyg_data.x, pyg_data.edge_index).numpy()

        # --------------------------------------------------------
        # 6. Transformation en score scalaire
        # --------------------------------------------------------
        # On réduit le vecteur en une valeur unique
        # via la norme L2
        scores = np.linalg.norm(embeddings, axis=1)

        # normalisation entre 0 et 1
        scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-8)

        # --------------------------------------------------------
        # 7. Construction de la sortie
        # --------------------------------------------------------
        return {
            nodes[i]: {
                "label": self.graph.nodes[nodes[i]].get("type", "unknown"),
                "score": float(scores[i]),

                # vecteur appris par le GNN
                "embedding": embeddings[i].tolist(),
            }
            for i in range(n)
        }

    # ============================================================
    # Backend fallback sans GNN
    # ============================================================

    def _predict_sklearn(self) -> Dict[str, Any]:
        """
        Ici, pas de vecteurs appris.
        On utilise uniquement des métriques de graphe.

        Les "scores" sont des combinaisons de :
        - centralité en degré
        - PageRank
        """
        G = self.graph

        degree_centrality = nx.degree_centrality(G)

        try:
            pagerank = nx.pagerank(G, alpha=0.85, max_iter=100)
        except Exception:
            pagerank = {n: 0.0 for n in G.nodes()}

        results = {}

        for node in G.nodes():
            ndata = G.nodes[node]

            score = (
                0.5 * degree_centrality.get(node, 0)
                + 0.5 * pagerank.get(node, 0)
            )

            results[node] = {
                "label": ndata.get("type", "unknown"),
                "score": round(score, 4),
                "in_degree": G.in_degree(node),
                "out_degree": G.out_degree(node),
            }

        return results

    # ============================================================

    @staticmethod
    def _check_pyg() -> bool:
        """
        Vérifie si PyTorch Geometric est installé.
        """
        try:
            import torch
            from torch_geometric.nn import SAGEConv
            return True
        except ImportError:
            return False