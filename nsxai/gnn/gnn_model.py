from __future__ import annotations
import argparse
import logging
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal

import networkx as nx
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Types publics ─────────────────────────────────────────────────────────────

@dataclass
class GNNResult:
    """Résultat de la génération d'embeddings."""
    node_profiles: Dict[str, Any]
    embeddings:    np.ndarray
    node_ids:      List[str]
    out_dir:       Optional[pathlib.Path] = None
    backend:       str = "unknown"
    embedding_dim: int = 0
    n_nodes:       int = 0
    success:       bool = False
    error:         Optional[str] = None

# ── Constantes ────────────────────────────────────────────────────────────────

_NODE_TYPES = ["class", "individual", "object_property", "datatype_property", "resource"]

# Colonnes littérales injectées par kg_builder (data properties du KG)
_LITERAL_FLOAT_COLS = [
    "metricValue", "metricExpectedValue", "loopQuality", "loopDifficulty",
    "masteryScore", "engagementIndex", "gdeCompatibilityScore",
    "numberOfViews", "numberOfFavorites", "rate", "value", "weight",
]
_LITERAL_CAT_COLS = [
    "difficulty", "level", "loopStatus",
    "archetypeBehavior", "archetypeBrainRegion",
]

# Valeurs connues pour l'encodage ordinal/one-hot des littéraux catégoriels
_CAT_VOCAB: Dict[str, List[str]] = {
    "difficulty":         ["easy", "medium", "hard", "expert"],
    "level":              ["easy", "medium", "hard", "expert"],
    "loopStatus":         ["pending", "active", "paused", "completed"],
    "archetypeBehavior":  ["survivor", "social", "cooperative", "exploratory", "achiever", "competitive"],
    "archetypeBrainRegion": ["cerebellum", "hippocampus", "prefrontal", "amygdala", "striatum"],
}

_EXPORT_FORMATS = Literal["csv", "json", "parquet", "numpy"]

# --- Chargement du graphe ---
def _load_graph(nodes_csv: pathlib.Path, edges_csv: pathlib.Path, log_fn: callable) -> nx.DiGraph:
    """Charge un graphe depuis des fichiers CSV de nœuds et d'arêtes."""
    nodes_df = pd.read_csv(nodes_csv)
    edges_df = pd.read_csv(edges_csv)
    G = nx.DiGraph()

    for _, row in nodes_df.iterrows():
        G.add_node(
            str(row["id"]),
            iri=str(row.get("iri", "")),
            type=str(row.get("type", "resource")),
            label=str(row.get("label", row["id"])),
        )

    for _, row in edges_df.iterrows():
        G.add_edge(
            str(row["source"]),
            str(row["target"]),
            relation=str(row.get("relation", "")),
            structural=bool(row.get("structural", False)),
        )

    log_fn(1, f"Graphe chargé : {G.number_of_nodes()} nœuds / {G.number_of_edges()} arêtes")
    return G

# ── Construction de la matrice de features ────────────────────────────────────

def _build_feature_matrix(G: nx.DiGraph) -> tuple[np.ndarray, list[str]]:
    """
    Construit une matrice de features pour les nœuds du graphe.

    Features incluses :
      - in_degree / out_degree (normalisés)
      - one-hot du type de nœud (5 catégories)
      - littéraux flottants du KG (metricValue, masteryScore, etc.)
      - encodage ordinal des littéraux catégoriels (difficulty, archetypeBehavior…)
    """
    nodes  = list(G.nodes())
    n      = len(nodes)
    type2idx = {t: i for i, t in enumerate(_NODE_TYPES)}

    max_in  = max((G.in_degree(v)  for v in nodes), default=1) or 1
    max_out = max((G.out_degree(v) for v in nodes), default=1) or 1

    n_float_feats = len(_LITERAL_FLOAT_COLS)
    n_cat_feats   = sum(len(v) for v in _CAT_VOCAB.values())
    n_cols        = 2 + len(_NODE_TYPES) + n_float_feats + n_cat_feats

    X = np.zeros((n, n_cols), dtype=np.float32)

    for i, node in enumerate(nodes):
        attrs = G.nodes[node]

        # Degree features
        X[i, 0] = G.in_degree(node)  / max_in
        X[i, 1] = G.out_degree(node) / max_out

        # Node-type one-hot
        ntype = attrs.get("type", "resource")
        X[i, 2 + type2idx.get(ntype, len(_NODE_TYPES) - 1)] = 1.0

        col = 2 + len(_NODE_TYPES)

        # Float literal features
        for fname in _LITERAL_FLOAT_COLS:
            raw = attrs.get(fname)
            if raw is not None:
                try:
                    X[i, col] = float(raw)
                except (ValueError, TypeError):
                    pass
            col += 1

        # Categorical literal features (one-hot per vocab)
        for cname, vocab in _CAT_VOCAB.items():
            raw = attrs.get(cname, "")
            if raw and raw in vocab:
                X[i, col + vocab.index(raw)] = 1.0
            col += len(vocab)

    return X, nodes

# --- Utilitaires ---
def _normalize_scores(scores: np.ndarray) -> np.ndarray:
    """Normalise les scores entre 0 et 1."""
    mn, mx = scores.min(), scores.max()
    return (scores - mn) / (mx - mn + 1e-8)

def _check_pyg() -> bool:
    """Vérifie si PyTorch Geometric est disponible."""
    try:
        import torch
        from torch_geometric.nn import SAGEConv
        return True
    except ImportError:
        return False

# --- Génération des embeddings (PyG) ---
def _generate_embeddings_pyg(G: nx.DiGraph, dim: int, log_fn: callable) -> tuple[np.ndarray, list[str], Dict[str, Any]]:
    """Génère des embeddings avec PyTorch Geometric."""
    import torch
    import torch.nn.functional as F
    from torch_geometric.data import Data
    from torch_geometric.nn import SAGEConv

    X, nodes = _build_feature_matrix(G)
    node2idx = {n: i for i, n in enumerate(nodes)}
    edges = list(G.edges())

    if not edges:
        log_fn(1, "Graphe sans arêtes → fallback sklearn")
        return _generate_embeddings_sklearn(G, dim, log_fn)

    src, dst = [node2idx[u] for u, v in edges], [node2idx[v] for u, v in edges]
    edge_index = torch.tensor([src, dst], dtype=torch.long)
    pyg_data = Data(x=torch.tensor(X), edge_index=edge_index)

    hidden = max(dim * 2, 32)
    class SAGE(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = SAGEConv(X.shape[1], hidden)
            self.conv2 = SAGEConv(hidden, dim)

        def forward(self, x, edge_index):
            x = F.relu(self.conv1(x, edge_index))
            return self.conv2(x, edge_index)

    model = SAGE()
    model.eval()
    with torch.no_grad():
        embeddings = model(pyg_data.x, pyg_data.edge_index).numpy()

    scores = _normalize_scores(np.linalg.norm(embeddings, axis=1))
    node_profiles = {
        nodes[i]: {
            "label": G.nodes[nodes[i]].get("type", "unknown"),
            "importance_score": float(scores[i]),
            "in_degree": G.in_degree(nodes[i]),
            "out_degree": G.out_degree(nodes[i]),
            "embedding": embeddings[i].tolist(),
        }
        for i in range(len(nodes))
    }
    return embeddings, nodes, node_profiles

# --- Génération des embeddings (sklearn) ---
def _generate_embeddings_sklearn(G: nx.DiGraph, dim: int, log_fn: callable) -> tuple[np.ndarray, list[str], Dict[str, Any]]:
    """Génère des embeddings avec scikit-learn (PCA + centralités)."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    nodes = list(G.nodes())
    n = len(nodes)
    X_feat, _ = _build_feature_matrix(G)

    try:
        pagerank = nx.pagerank(G, alpha=0.85, max_iter=200)
    except Exception:
        pagerank = {v: 1.0 / n for v in nodes}

    try:
        betweenness = nx.betweenness_centrality(G, normalized=True, k=min(n, 100))
    except Exception:
        betweenness = {v: 0.0 for v in nodes}

    degree_c = nx.degree_centrality(G)
    extra = np.array([[pagerank.get(v, 0), betweenness.get(v, 0), degree_c.get(v, 0)] for v in nodes], dtype=np.float32)
    X_full = np.hstack([X_feat, extra])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_full)
    actual_dim = min(dim, X_full.shape[0] - 1, X_full.shape[1])
    pca = PCA(n_components=actual_dim, random_state=42)
    embeddings_pca = pca.fit_transform(X_scaled).astype(np.float32)

    if actual_dim < dim:
        pad = np.zeros((n, dim - actual_dim), dtype=np.float32)
        embeddings = np.hstack([embeddings_pca, pad])
    else:
        embeddings = embeddings_pca

    scores = _normalize_scores(
        0.5 * np.array([degree_c.get(v, 0) for v in nodes]) +
        0.5 * np.array([pagerank.get(v, 0) for v in nodes])
    )

    node_profiles = {
        nodes[i]: {
            "label": G.nodes[nodes[i]].get("type", "unknown"),
            "importance_score": float(scores[i]),
            "in_degree": G.in_degree(nodes[i]),
            "out_degree": G.out_degree(nodes[i]),
            "embedding": embeddings[i].tolist(),
        }
        for i in range(n)
    }
    return embeddings, nodes, node_profiles

# --- Export des embeddings ---
def _export_embeddings_csv(
    embeddings: np.ndarray,
    node_ids: list[str],
    node_profiles: Dict[str, Any],
    out_dir: pathlib.Path,
    log_fn: callable,
) -> None:
    """Exporte les embeddings et profils en CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "embeddings.csv"
    rows = []
    for i, node_id in enumerate(node_ids):
        row = {
            "node_id": node_id,
            "label": node_profiles[node_id]["label"],
            "importance_score": node_profiles[node_id]["importance_score"],
        }
        for j in range(embeddings.shape[1]):
            row[f"dim_{j}"] = embeddings[i, j]
        rows.append(row)
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    log_fn(1, f"Embeddings exportés en CSV : {csv_path}")

def _export_embeddings_json(
    embeddings: np.ndarray,
    node_ids: list[str],
    node_profiles: Dict[str, Any],
    out_dir: pathlib.Path,
    log_fn: callable,
) -> None:
    """Exporte les embeddings et profils en JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "embeddings.json"
    export_data = {
        "node_ids": node_ids,
        "embeddings": embeddings.tolist(),
        "node_profiles": node_profiles,
        "metadata": {
            "n_nodes": len(node_ids),
            "embedding_dim": embeddings.shape[1],
        },
    }
    import json
    with open(json_path, "w") as f:
        json.dump(export_data, f, indent=2)
    log_fn(1, f"Embeddings exportés en JSON : {json_path}")

def _export_embeddings_parquet(
    embeddings: np.ndarray,
    node_ids: list[str],
    node_profiles: Dict[str, Any],
    out_dir: pathlib.Path,
    log_fn: callable,
) -> None:
    """Exporte les embeddings et profils en Parquet."""
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "embeddings.parquet"
    rows = []
    for i, node_id in enumerate(node_ids):
        row = {
            "node_id": node_id,
            "label": node_profiles[node_id]["label"],
            "importance_score": node_profiles[node_id]["importance_score"],
            **{f"dim_{j}": embeddings[i, j] for j in range(embeddings.shape[1])},
        }
        rows.append(row)
    pd.DataFrame(rows).to_parquet(parquet_path, index=False)
    log_fn(1, f"Embeddings exportés en Parquet : {parquet_path}")

def _export_embeddings_numpy(
    embeddings: np.ndarray,
    node_ids: list[str],
    node_profiles: Dict[str, Any],
    out_dir: pathlib.Path,
    log_fn: callable,
) -> None:
    """Exporte les embeddings en format NumPy (.npy et .npz)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    npy_path = out_dir / "embeddings.npy"
    npz_path = out_dir / "embeddings_metadata.npz"

    np.save(npy_path, embeddings)
    np.savez(
        npz_path,
        node_ids=node_ids,
        node_profiles=node_profiles,
        embedding_dim=embeddings.shape[1],
        n_nodes=len(node_ids),
    )
    log_fn(1, f"Embeddings exportés en NumPy : {npy_path} et {npz_path}")

def _export_embeddings(
    embeddings: np.ndarray,
    node_ids: list[str],
    node_profiles: Dict[str, Any],
    out_dir: pathlib.Path,
    log_fn: callable,
    formats: list[_EXPORT_FORMATS] = ["csv", "json", "parquet", "numpy"],
) -> None:
    """Exporte les embeddings dans les formats spécifiés."""
    for fmt in formats:
        if fmt == "csv":
            _export_embeddings_csv(embeddings, node_ids, node_profiles, out_dir, log_fn)
        elif fmt == "json":
            _export_embeddings_json(embeddings, node_ids, node_profiles, out_dir, log_fn)
        elif fmt == "parquet":
            _export_embeddings_parquet(embeddings, node_ids, node_profiles, out_dir, log_fn)
        elif fmt == "numpy":
            _export_embeddings_numpy(embeddings, node_ids, node_profiles, out_dir, log_fn)

# --- API publique ---
def run_gnn(
    nodes_csv: str,
    edges_csv: str,
    out_dir: str = "output/embeddings",
    dim: int = 16,
    verbose: bool = False,
    quiet: bool = False,
    export_formats: list[_EXPORT_FORMATS] = ["csv", "json", "parquet", "numpy"],
) -> GNNResult:
    """
    Exécute la génération d'embeddings pour un graphe donné.

    Args:
        nodes_csv: Chemin vers le fichier CSV des nœuds.
        edges_csv: Chemin vers le fichier CSV des arêtes.
        out_dir: Dossier de sortie pour les embeddings.
        dim: Dimension des embeddings.
        verbose: Mode verbeux.
        quiet: Mode silencieux.
        export_formats: Liste des formats d'export (csv, json, parquet, numpy).
    """
    nodes_path, edges_path, out_path = pathlib.Path(nodes_csv), pathlib.Path(edges_csv), pathlib.Path(out_dir)
    log_level = 0 if quiet else (2 if verbose else 1)

    def log_fn(level: int, msg: str) -> None:
        if log_level >= level:
            print(msg, flush=True)

    result = GNNResult(node_profiles={}, embeddings=np.empty((0, dim)), node_ids=[])

    try:
        G = _load_graph(nodes_path, edges_path, log_fn)
        use_pyg = _check_pyg()
        backend = "pyg" if use_pyg else "sklearn"
        log_fn(1, f"Backend : {backend}")

        if use_pyg:
            embeddings, node_ids, node_profiles = _generate_embeddings_pyg(G, dim, log_fn)
        else:
            embeddings, node_ids, node_profiles = _generate_embeddings_sklearn(G, dim, log_fn)

        _export_embeddings(embeddings, node_ids, node_profiles, out_path, log_fn, export_formats)

        result.node_profiles = node_profiles
        result.embeddings = embeddings
        result.node_ids = node_ids
        result.out_dir = out_path
        result.backend = backend
        result.embedding_dim = embeddings.shape[1]
        result.n_nodes = len(node_ids)
        result.success = True
        log_fn(1, f"Terminé : {result.n_nodes} nœuds / dim={result.embedding_dim}")

    except Exception as exc:
        result.error = str(exc)
        log_fn(0, f"[ERREUR] {exc}")

    return result

"""
gnn_model.py — Génération d'embeddings et de features à partir d'un graphe.
Utilisation possible avec RandomForest, XGBoost, SVM, ou un vrai GNN supervisé.

TODO: ------------------------------------------------------------------------
    UTILISATION DES EMBEDDINGS GÉNÉRÉS :
    ------------------------------------------------------------------------
    Après la génération des embeddings, voici comment les importer et les utiliser
    dans différents contextes. Les embeddings sont exportés dans plusieurs formats
    (CSV, JSON, Parquet, NumPy). Voici comment les charger et les exploiter.

    --- 1. IMPORTATION DES EMBEDDINGS ---
    Selon le format d'export, utilisez l'une des méthodes suivantes :

    1.1. Depuis un fichier CSV :
        ```python
        import pandas as pd
        import numpy as np

        # Charger le fichier CSV
        df = pd.read_csv("output/embeddings/embeddings.csv")

        # Extraire les embeddings (colonnes dim_0, dim_1, ...)
        embeddings = df.filter(like="dim_").values  # Matrice NumPy (n_nodes x embedding_dim)

        # Extraire les IDs des nœuds et les métadonnées
        node_ids = df["node_id"].values
        labels = df["label"].values
        importance_scores = df["importance_score"].values
        ```

    1.2. Depuis un fichier JSON :
        ```python
        import json
        import numpy as np

        with open("output/embeddings/embeddings.json", "r") as f:
            data = json.load(f)

        embeddings = np.array(data["embeddings"])  # Matrice NumPy
        node_ids = data["node_ids"]
        node_profiles = data["node_profiles"]  # Dictionnaire complet des profils
        metadata = data["metadata"]  # Métadonnées (n_nodes, embedding_dim, etc.)
        ```

    1.3. Depuis un fichier Parquet :
        ```python
        import pandas as pd

        df = pd.read_parquet("output/embeddings/embeddings.parquet")
        embeddings = df.filter(like="dim_").values
        node_ids = df["node_id"].values
        ```

    1.4. Depuis un fichier NumPy (.npy et .npz) :
        ```python
        import numpy as np

        # Charger les embeddings
        embeddings = np.load("output/embeddings/embeddings.npy")

        # Charger les métadonnées (node_ids, node_profiles, etc.)
        metadata = np.load("output/embeddings/embeddings_metadata.npz", allow_pickle=True)
        node_ids = metadata["node_ids"]
        node_profiles = metadata["node_profiles"].item()  # Convertir en dict
        ```

    --- 2. PRÉTRAITEMENT POUR LES MODÈLES DE ML CLASSIQUE ---
    Les embeddings peuvent être utilisés directement comme features dans des modèles
    de machine learning classiques. Assurez-vous que les labels (classes) sont alignés
    avec les node_ids.

    2.1. Exemple avec RandomForest :
        ```python
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report

        # Supposons que vous avez un tableau `labels` avec les classes pour chaque nœud
        # (à aligner avec `node_ids` si nécessaire)
        X_train, X_test, y_train, y_test = train_test_split(embeddings, labels, test_size=0.2)

        clf = RandomForestClassifier(n_estimators=100, random_state=42)
        clf.fit(X_train, y_train)

        y_pred = clf.predict(X_test)
        print(classification_report(y_test, y_pred))
        ```

    2.2. Exemple avec XGBoost :
        ```python
        import xgboost as xgb
        from sklearn.metrics import accuracy_score

        model = xgb.XGBClassifier(objective="multi\:softmax", num_class=len(set(labels)))
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        print(f"Accuracy: {accuracy_score(y_test, y_pred)}")
        ```

    2.3. Exemple avec SVM :
        ```python
        from sklearn.svm import SVC
        from sklearn.preprocessing import StandardScaler

        # Normalisation des embeddings (recommandé pour SVM)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        svm = SVC(kernel="rbf", random_state=42)
        svm.fit(X_train_scaled, y_train)

        y_pred = svm.predict(X_test_scaled)
        print(f"Accuracy: {accuracy_score(y_test, y_pred)}")
        ```

    --- 3. UTILISATION DANS UN GNN SUPERVISÉ ---
    Les embeddings peuvent servir de features d'entrée pour un modèle GNN supervisé.
    Voici comment les intégrer dans un pipeline PyTorch Geometric.

    3.1. Préparation des données pour PyG :
        ```python
        import torch
        from torch_geometric.data import Data

        # Supposons que vous avez déjà :
        # - embeddings : matrice NumPy des embeddings (n_nodes x embedding_dim)
        # - edges : liste des arêtes du graphe (ex: [(source, target), ...])

        # Convertir les embeddings en tensor PyTorch
        x = torch.tensor(embeddings, dtype=torch.float)

        # Créer edge_index pour PyG (format COO)
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()

        # Créer un objet Data pour PyG
        data = Data(x=x, edge_index=edge_index)
        ```

    3.2. Définition d'un modèle GNN (ex: GraphSAGE) :
        ```python
        import torch.nn as nn
        import torch.nn.functional as F
        from torch_geometric.nn import SAGEConv

        class GNN(nn.Module):
            def __init__(self, input_dim, hidden_dim, output_dim):
                super().__init__()
                self.conv1 = SAGEConv(input_dim, hidden_dim)
                self.conv2 = SAGEConv(hidden_dim, output_dim)

            def forward(self, data):
                x, edge_index = data.x, data.edge_index
                x = F.relu(self.conv1(x, edge_index))
                x = self.conv2(x, edge_index)
                return x

        # Initialiser le modèle
        model = GNN(input_dim=embeddings.shape[1], hidden_dim=64, output_dim=num_classes)
        ```

    3.3. Entraînement du modèle :
        ```python
        from torch_geometric.loader import DataLoader

        # Supposons que vous avez des labels pour chaque nœud
        data.y = torch.tensor(labels, dtype=torch.long)

        # Créer un DataLoader (pour batch training)
        loader = DataLoader([data], batch_size=1, shuffle=True)

        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(100):
            for batch in loader:
                optimizer.zero_grad()
                out = model(batch)
                loss = criterion(out, batch.y)
                loss.backward()
                optimizer.step()
            print(f"Epoch {epoch}, Loss: {loss.item()}")
        ```

    --- 4. VISUALISATION DES EMBEDDINGS ---
    Utilisez des techniques de réduction de dimension pour visualiser les clusters
    ou les relations entre les nœuds.

    4.1. Avec UMAP :
        ```python
        from umap import UMAP
        import matplotlib.pyplot as plt

        reducer = UMAP(n_components=2, random_state=42)
        reduced_embeddings = reducer.fit_transform(embeddings)

        plt.figure(figsize=(10, 8))
        plt.scatter(reduced_embeddings[:, 0], reduced_embeddings[:, 1], alpha=0.5)
        plt.title("UMAP Visualization of Embeddings")
        plt.xlabel("UMAP Dimension 1")
        plt.ylabel("UMAP Dimension 2")
        plt.show()
        ```

    4.2. Avec t-SNE :
        ```python
        from sklearn.manifold import TSNE

        tsne = TSNE(n_components=2, random_state=42)
        reduced_embeddings = tsne.fit_transform(embeddings)

        plt.figure(figsize=(10, 8))
        plt.scatter(reduced_embeddings[:, 0], reduced_embeddings[:, 1], alpha=0.5)
        plt.title("t-SNE Visualization of Embeddings")
        plt.show()
        ```

    4.3. Avec coloration par label ou cluster :
        ```python
        # Supposons que vous avez des labels ou des clusters
        plt.figure(figsize=(10, 8))
        scatter = plt.scatter(
            reduced_embeddings[:, 0],
            reduced_embeddings[:, 1],
            c=labels,  # ou clusters
            cmap="viridis",
            alpha=0.7
        )
        plt.colorbar(scatter)
        plt.title("UMAP Visualization with Labels")
        plt.show()
        ```

    --- 5. CLUSTERING NON SUPERVISÉ ---
    Utilisez des algorithmes de clustering pour regrouper les nœuds en fonction
    de leurs embeddings.

    5.1. Avec K-Means :
        ```python
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        kmeans = KMeans(n_clusters=5, random_state=42)
        clusters = kmeans.fit_predict(embeddings)

        # Évaluer la qualité du clustering
        silhouette_avg = silhouette_score(embeddings, clusters)
        print(f"Silhouette Score: {silhouette_avg}")
        ```

    5.2. Avec DBSCAN (pour des clusters de densité variable) :
        ```python
        from sklearn.cluster import DBSCAN

        dbscan = DBSCAN(eps=0.5, min_samples=5)
        clusters = dbscan.fit_predict(embeddings)

        # Nombre de clusters (exclut le bruit, label = -1)
        n_clusters = len(set(clusters)) - (1 if -1 in clusters else 0)
        print(f"Nombre de clusters: {n_clusters}")
        ```

    5.3. Visualisation des clusters :
        ```python
        plt.figure(figsize=(10, 8))
        scatter = plt.scatter(
            reduced_embeddings[:, 0],
            reduced_embeddings[:, 1],
            c=clusters,
            cmap="viridis",
            alpha=0.7
        )
        plt.colorbar(scatter)
        plt.title("Clusters Visualization (UMAP + K-Means)")
        plt.show()
        ```

    --- 6. RECHERCHE DE SIMILARITÉ ---
    Calculez la similarité entre les nœuds pour trouver des nœuds similaires
    ou effectuer des recherches par similarité.

    6.1. Similarité cosinus :
        ```python
        from sklearn.metrics.pairwise import cosine_similarity

        # Calculer la matrice de similarité
        similarity_matrix = cosine_similarity(embeddings)

        # Exemple: Trouver les 5 nœuds les plus similaires à un nœud donné
        node_index = 0  # Index du nœud de référence
        similarities = similarity_matrix[node_index]
        top_similar_indices = similarities.argsort()[-6:-1][::-1]  # Top 5 (exclut le nœud lui-même)

        print(f"Top 5 similar nodes to {node_ids[node_index]}:")
        for idx in top_similar_indices:
            print(f"- {node_ids[idx]} (similarity: {similarities[idx]:.4f})")
        ```

    6.2. Similarité avec FAISS (pour les grands graphes) :
        ```python
        import faiss

        # Créer un index FAISS
        index = faiss.IndexFlatL2(embeddings.shape[1])  # Distance L2
        index.add(embeddings.astype("float32"))

        # Rechercher les k plus proches voisins
        k = 5
        distances, indices = index.search(embeddings[node_index].reshape(1, -1).astype("float32"), k)

        print(f"Top {k} similar nodes to {node_ids[node_index]}:")
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            print(f"- {node_ids[idx]} (distance: {dist:.4f})")
        ```

    --- 7. INTÉGRATION DANS UNE PIPELINE ML ---
    Sauvegardez et chargez les embeddings pour une réutilisation rapide dans une pipeline.

    7.1. Sauvegarde avec joblib :
        ```python
        import joblib

        # Sauvegarder
        joblib.dump(embeddings, "embeddings.pkl")
        joblib.dump(node_ids, "node_ids.pkl")
        joblib.dump(labels, "labels.pkl")

        # Charger
        embeddings_loaded = joblib.load("embeddings.pkl")
        node_ids_loaded = joblib.load("node_ids.pkl")
        labels_loaded = joblib.load("labels.pkl")
        ```

    7.2. Sauvegarde avec pickle :
        ```python
        import pickle

        # Sauvegarder
        with open("embeddings_data.pkl", "wb") as f:
            pickle.dump({"embeddings": embeddings, "node_ids": node_ids, "labels": labels}, f)

        # Charger
        with open("embeddings_data.pkl", "rb") as f:
            data = pickle.load(f)
            embeddings_loaded = data["embeddings"]
            node_ids_loaded = data["node_ids"]
        ```

    --- 8. UTILISATION DANS DES APPLICATIONS WEB ---
    Exportez les embeddings en JSON pour une utilisation côté frontend (ex: visualisation avec D3.js).

    8.1. Préparation des données pour le frontend :
        ```python
        import json

        # Préparer les données pour D3.js
        export_data = {
            "nodes": [
                {"id": node_id, "label": node_profiles[node_id]["label"]}
                for node_id in node_ids
            ],
            "embeddings": embeddings.tolist(),
            "metadata": {
                "embedding_dim": embeddings.shape[1],
                "n_nodes": len(node_ids),
            }
        }

        with open("embeddings_for_web.json", "w") as f:
            json.dump(export_data, f, indent=2)
        ```

    8.2. Exemple de visualisation avec D3.js (à intégrer dans une page HTML) :
        ```html
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://d3js.org/d3.v7.min.js"></script>
            <style>
                .node circle { fill: #fff; stroke: steelblue; stroke-width: 2px; }
                .node text { font: 12px sans-serif; }
                .link { fill: none; stroke: #ccc; stroke-width: 1.5px; }
            </style>
        </head>
        <body>
            <svg width="800" height="600"></svg>
            <script>
                // Charger les données depuis embeddings_for_web.json
                d3.json("embeddings_for_web.json").then(function(data) {
                    const svg = d3.select("svg");
                    const width = +svg.attr("width");
                    const height = +svg.attr("height");

                    // Réduire les dimensions des embeddings à 2D pour la visualisation
                    // (à faire côté backend ou avec une librairie comme UMAP en JS)
                    const nodes = data.nodes.map((d, i) => ({
                        id: d.id,
                        label: d.label,
                        x: data.embeddings[i][0],  // Supposons que les embeddings sont déjà en 2D
                        y: data.embeddings[i][1]
                    }));

                    // Créer une simulation de force pour le graphe
                    const simulation = d3.forceSimulation(nodes)
                        .force("charge", d3.forceManyBody().strength(-100))
                        .force("link", d3.forceLink().id(d => d.id))
                        .force("center", d3.forceCenter(width / 2, height / 2));

                    // Dessiner les nœuds
                    const node = svg.selectAll(".node")
                        .data(nodes)
                        .enter().append("g")
                        .attr("class", "node")
                        .call(d3.drag()
                            .on("start", dragstarted)
                            .on("drag", dragged)
                            .on("end", dragended));

                    node.append("circle").attr("r", 10);
                    node.append("text")
                        .text(d => d.label)
                        .attr("dy", 20)
                        .attr("text-anchor", "middle");

                    // Mettre à jour les positions à chaque tick
                    simulation.on("tick", () => {
                        node.attr("transform", d => `translate(${d.x},${d.y})`);
                    });

                    function dragstarted(event, d) {
                        if (!event.active) simulation.alphaTarget(0.3).restart();
                        d.fx = d.x;
                        d.fy = d.y;
                    }

                    function dragged(event, d) {
                        d.fx = event.x;
                        d.fy = event.y;
                    }

                    function dragended(event, d) {
                        if (!event.active) simulation.alphaTarget(0);
                        d.fx = null;
                        d.fy = null;
                    }
                });
            </script>
        </body>
        </html>
        ```

    --- 9. BONNES PRATIQUES ---
    9.1. Normalisation des embeddings :
        - Les embeddings générés sont déjà normalisés, mais vous pouvez les re-normaliser
          si nécessaire :
          ```python
          from sklearn.preprocessing import MinMaxScaler

          scaler = MinMaxScaler()
          embeddings_normalized = scaler.fit_transform(embeddings)
          ```

    9.2. Réduction de dimension pour la visualisation :
        - Utilisez UMAP ou t-SNE pour réduire la dimension à 2 ou 3 pour la visualisation :
          ```python
          from umap import UMAP

          reducer = UMAP(n_components=2)
          embeddings_2d = reducer.fit_transform(embeddings)
          ```

    9.3. Sauvegarde des modèles entraînés :
        - Si vous entraînez un modèle sur les embeddings, sauvegardez-le pour une réutilisation :
          ```python
          import joblib

          # Sauvegarder le modèle
          joblib.dump(clf, "random_forest_model.pkl")

          # Charger le modèle
          model_loaded = joblib.load("random_forest_model.pkl")
          ```

    9.4. Utilisation avec des frameworks de deep learning :
        - Convertir les embeddings en tensors pour PyTorch ou TensorFlow :
          ```python
          # PyTorch
          import torch
          embeddings_tensor = torch.tensor(embeddings, dtype=torch.float32)

          # TensorFlow
          import tensorflow as tf
          embeddings_tensor = tf.convert_to_tensor(embeddings, dtype=tf.float32)
          ```

    ------------------------------------------------------------------------
    EXPORT DES EMBEDDINGS :
    - Les embeddings sont exportés par défaut en CSV, JSON, Parquet et NumPy.
    - Pour choisir les formats d'export, utilisez le paramètre `export_formats` dans `run_gnn` :
      ```python
      run_gnn(nodes_csv, edges_csv, export_formats=["csv", "json"])
      ```
    ------------------------------------------------------------------------
"""
