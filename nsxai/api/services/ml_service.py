import os
import numpy as np
import networkx as nx
from typing import List, Dict, Tuple
from .fuseki import fuseki_client
import logging

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
    DEVICE = torch.device("cpu") # Inférence légère sur CPU par défaut
except ImportError:
    TORCH_AVAILABLE = False
    DEVICE = None
    # Dummy mock pour éviter que la définition des classes plante au chargement du module
    class DummyNN:
        class Module:
            pass
        def Linear(self, *args, **kwargs): pass
        def Dropout(self, *args, **kwargs): pass
        def Sequential(self, *args, **kwargs): pass
        def ReLU(self, *args, **kwargs): pass
    nn = DummyNN()
    class DummyF:
        def relu(self, *args, **kwargs): pass
    F = DummyF()

# ── Modèles PyTorch (GCN) ──

class GCNLayer(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.linear = nn.Linear(in_dim, out_dim)
    def forward(self, x, adj_norm):
        return F.relu(self.linear(torch.matmul(adj_norm, x)))

class GCNEncoder(nn.Module):
    def __init__(self, in_dim, hidden_dim=32, embedding_dim=16, dropout=0.5):
        super().__init__()
        self.layer1  = GCNLayer(in_dim, hidden_dim)
        self.layer2  = GCNLayer(hidden_dim, embedding_dim)
        self.dropout = nn.Dropout(dropout)
    def forward(self, x, adj_norm):
        return self.layer2(self.dropout(self.layer1(x, adj_norm)), adj_norm)

class LinkDecoder(nn.Module):
    def __init__(self, embedding_dim=32, heuristic_dim=10, hidden_dim=64):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(embedding_dim * 4 + heuristic_dim, hidden_dim),
            nn.ReLU(), nn.Dropout(0.25),
            nn.Linear(hidden_dim, 1),
        )
    def forward(self, z_src, z_dst, heuristics):
        pair = torch.cat([z_src, z_dst, torch.abs(z_src-z_dst), z_src*z_dst, heuristics], dim=1)
        return self.mlp(pair).squeeze(-1)

class GCNLinkPredictionModel(nn.Module):
    def __init__(self, in_dim, hidden_dim=32, embedding_dim=16):
        super().__init__()
        self.encoder = GCNEncoder(in_dim, hidden_dim, embedding_dim)
        self.decoder = LinkDecoder(embedding_dim, heuristic_dim=10)
    def forward(self, x, adj_norm, src_idx, dst_idx, heuristics):
        z = self.encoder(x, adj_norm)
        return self.decoder(z[src_idx], z[dst_idx], heuristics)

class GraphSAGELayer(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.self_linear  = nn.Linear(in_dim, out_dim)
        self.neigh_linear = nn.Linear(in_dim, out_dim)
    def forward(self, x, adj_norm):
        return F.relu(self.self_linear(x) + self.neigh_linear(torch.matmul(adj_norm, x)))

class GraphSAGEEncoder(nn.Module):
    def __init__(self, in_dim, hidden_dim=32, embedding_dim=16, dropout=0.5):
        super().__init__()
        self.layer1  = GraphSAGELayer(in_dim, hidden_dim)
        self.layer2  = GraphSAGELayer(hidden_dim, embedding_dim)
        self.dropout = nn.Dropout(dropout)
    def forward(self, x, adj_norm):
        return self.layer2(self.dropout(self.layer1(x, adj_norm)), adj_norm)

class GraphSAGELinkPredictionModel(nn.Module):
    def __init__(self, in_dim, hidden_dim=32, embedding_dim=16):
        super().__init__()
        self.encoder = GraphSAGEEncoder(in_dim, hidden_dim, embedding_dim)
        self.decoder = LinkDecoder(embedding_dim, heuristic_dim=10)
    def forward(self, x, adj_norm, src_idx, dst_idx, heuristics):
        z = self.encoder(x, adj_norm)
        return self.decoder(z[src_idx], z[dst_idx], heuristics)

class PairMLP(nn.Module):
    def __init__(self, input_dim, hidden_dim=128):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(), nn.Dropout(0.25),
            nn.Linear(hidden_dim, hidden_dim // 2), nn.ReLU(), nn.Dropout(0.25),
            nn.Linear(hidden_dim // 2, 1),
        )
    def forward(self, x):
        return self.network(x).squeeze(-1)


# ── Service d'Inférence Backend ──

class MLPredictorService:
    def __init__(self):
        self.model = None
        self.is_loaded = False
        self.active_model_name = "GCN_LP.pt" # par défaut
        self.model_type = "GCN" # GCN, GraphSAGE, MLP, SKLEARN, XGBOOST
        
        # État du graphe
        self.G_mp = None
        self.G_undirected = None
        self.node_to_idx = {}
        self.idx_to_node = {}
        self.X_nodes = None
        self.adj_norm = None
        
        # Caches heuristiques
        self.clustering_cache = {}
        self.pagerank = {}
        self.type_pair_to_idx = {}
        self.node_types_map = {}
        
        self.load_model()

    def set_active_model(self, model_name: str):
        """Permet de changer le modèle actif à la volée."""
        self.active_model_name = model_name
        self.load_model()
        
    def get_model_path(self):
        return os.path.join(os.path.dirname(__file__), "../../../model/output_files/exported_models/seed_42", self.active_model_name)

    def load_model(self):
        """Charge le modèle sélectionné."""
        path_to_load = self.get_model_path()
        if not os.path.exists(path_to_load):
            logger.warning(f"Modèle {self.active_model_name} introuvable dans {path_to_load}.")
            self.is_loaded = False
            return

        name_lower = self.active_model_name.lower()
        if "gcn" in name_lower: self.model_type = "GCN"
        elif "graphsage" in name_lower: self.model_type = "GraphSAGE"
        elif "mlp" in name_lower: self.model_type = "MLP"
        elif "xgboost" in name_lower: self.model_type = "XGBOOST"
        else: self.model_type = "SKLEARN"

        if self.model_type in ["GCN", "GraphSAGE", "MLP"] and not TORCH_AVAILABLE:
            logger.warning(f"PyTorch n'est pas installé. L'inférence ML pour {self.model_type} sera désactivée.")
            self.is_loaded = False
            return

        try:
            self._model_path = path_to_load
            
            # Pour XGBoost et Sklearn, on peut charger immédiatement
            if self.model_type == "SKLEARN":
                import joblib
                self.model = joblib.load(self._model_path)
            elif self.model_type == "XGBOOST":
                import xgboost as xgb
                self.model = xgb.Booster()
                self.model.load_model(self._model_path)
            # Pour PyTorch, on charge au moment du sync (car on a besoin de in_dim)
            
            self.is_loaded = True
            logger.info(f"Modèle ML ({self.model_type}) activé : {self.active_model_name}")
        except Exception as e:
            logger.error(f"Erreur de chargement du modèle {self.active_model_name}: {e}")
            self.is_loaded = False

    def sync_graph(self):
        """Synchronise le graphe NetworkX depuis Fuseki et construit les features ML."""
        if not self.is_loaded:
            return

        logger.info("Synchronisation du graphe pour le ML...")
        query = """
        SELECT DISTINCT ?s ?p ?o ?sType ?oType WHERE {
            ?s ?p ?o .
            FILTER(isIRI(?s) && isIRI(?o))
            FILTER(?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
            OPTIONAL { ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?sType }
            OPTIONAL { ?o <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?oType }
        }
        """
        try:
            results = fuseki_client.query(query)["results"]["bindings"]
        except Exception as e:
            logger.error(f"Erreur SPARQL lors de la sync ML: {e}")
            return

        self.G_mp = nx.DiGraph()
        
        # Build node types map
        node_types_map = {}
        for b in results:
            s, o = b["s"]["value"], b["o"]["value"]
            self.G_mp.add_node(s)
            self.G_mp.add_node(o)
            self.G_mp.add_edge(s, o)
            if "sType" in b: node_types_map[s] = b["sType"]["value"]
            if "oType" in b: node_types_map[o] = b["oType"]["value"]

        self.node_types_map = node_types_map

        # Reconstruire type_pair_to_idx dynamiquement
        type_pairs = sorted(list(set({
            f"{node_types_map.get(u, '?')}_{node_types_map.get(v, '?')}"
            for u, v in self.G_mp.edges()
        })))
        self.type_pair_to_idx = {tp: idx for idx, tp in enumerate(type_pairs)}

        # ── Features Nœuds ──
        node_ids = list(self.G_mp.nodes())
        if len(node_ids) == 0:
            return
            
        self.node_to_idx = {n: i for i, n in enumerate(node_ids)}
        self.idx_to_node = {i: n for i, n in enumerate(node_ids)}
        self.G_undirected = self.G_mp.to_undirected()
        
        logger.info("Calcul des heuristiques globales (PageRank, Centrality)...")
        self.clustering_cache = nx.clustering(self.G_undirected)
        self.pagerank = nx.pagerank(self.G_mp)
        degree_centrality = nx.degree_centrality(self.G_mp)
        
        # Types uniques
        all_types = sorted(list(set(node_types_map.values())))
        
        features = []
        for n in node_ids:
            row = [
                self.G_mp.in_degree(n),
                self.G_mp.out_degree(n),
                degree_centrality.get(n, 0.0),
                self.pagerank.get(n, 0.0)
            ]
            ntype = node_types_map.get(n, "unknown")
            type_onehot = [1.0 if ntype == t else 0.0 for t in all_types]
            features.append(row + type_onehot)
            
        features_np = np.array(features, dtype=np.float32)
        # Standardisation basique
        num_cols = features_np[:, :4]
        means = num_cols.mean(axis=0)
        stds = num_cols.std(axis=0)
        stds[stds == 0] = 1.0
        features_np[:, :4] = (num_cols - means) / stds
        
        if TORCH_AVAILABLE:
            self.X_nodes = torch.tensor(features_np, dtype=torch.float32).to(DEVICE)
            
            # ── Adjacency Normalisée ──
            n_nodes = len(node_ids)
            adj = torch.zeros((n_nodes, n_nodes), dtype=torch.float32)
            for u, v in self.G_mp.edges():
                adj[self.node_to_idx[u], self.node_to_idx[v]] = 1.0
                adj[self.node_to_idx[v], self.node_to_idx[u]] = 1.0
            adj += torch.eye(n_nodes)
            self.adj_norm = (adj / adj.sum(dim=1, keepdim=True).clamp(min=1.0)).to(DEVICE)

            # Instantiate & Load PyTorch models
            in_dim = self.X_nodes.shape[1]
            try:
                if self.model_type == "GCN":
                    self.model = GCNLinkPredictionModel(in_dim=in_dim).to(DEVICE)
                elif self.model_type == "GraphSAGE":
                    self.model = GraphSAGELinkPredictionModel(in_dim=in_dim).to(DEVICE)
                elif self.model_type == "MLP":
                    # dimensions : (node_feat * 2) + 1 (same_type) + len(type_pair_to_idx) + heur_dim
                    feat_dim = (in_dim * 2) + 1 + len(self.type_pair_to_idx) + 10
                    self.model = PairMLP(input_dim=feat_dim).to(DEVICE)
                
                if self.model_type in ["GCN", "GraphSAGE", "MLP"]:
                    self.model.load_state_dict(torch.load(self._model_path, map_location=DEVICE), strict=False)
                    self.model.eval()
                    logger.info(f"Modèle PyTorch {self.model_type} chargé en mémoire et graphe synchronisé !")
            except Exception as e:
                logger.error(f"Erreur de chargement des poids PyTorch: {e}")
                self.is_loaded = False
        
        self.features_np_cache = features_np

    def _compute_heuristics(self, u, v):
        try:    aa = next(nx.adamic_adar_index(self.G_undirected, [(u,v)]))[2]
        except: aa = 0.0
        try:    jc = next(nx.jaccard_coefficient(self.G_undirected, [(u,v)]))[2]
        except: jc = 0.0
        try:    pa = next(nx.preferential_attachment(self.G_undirected, [(u,v)]))[2]
        except: pa = 0.0
        try:    cn = len(list(nx.common_neighbors(self.G_undirected, u, v)))
        except: cn = 0

        try:    sp = nx.shortest_path_length(self.G_undirected, u, v)
        except: sp = 999

        n2_u = set(n for nb in self.G_undirected.neighbors(u) for n in self.G_undirected.neighbors(nb)) - {u}
        n2_v = set(n for nb in self.G_undirected.neighbors(v) for n in self.G_undirected.neighbors(nb)) - {v}
        cn2 = len(n2_u & n2_v)

        try:    ra = next(nx.resource_allocation_index(self.G_undirected, [(u,v)]))[2]
        except: ra = 0.0

        cc_u = self.clustering_cache.get(u, 0.0)
        cc_v = self.clustering_cache.get(v, 0.0)
        pr_diff = abs(self.pagerank.get(u, 0.0) - self.pagerank.get(v, 0.0))

        return [aa, jc, pa, cn, sp, cn2, ra, cc_u, cc_v, pr_diff]

    def _build_pair_features(self, u, v, h):
        """Reconstruit le vecteur exact attendu par MLP, XGBoost, Random Forest."""
        idx_u = self.node_to_idx[u]
        idx_v = self.node_to_idx[v]
        feat_u = self.features_np_cache[idx_u]
        feat_v = self.features_np_cache[idx_v]
        
        same_type = 1.0 if self.node_types_map.get(u) == self.node_types_map.get(v) else 0.0
        tp_key = f"{self.node_types_map.get(u, '?')}_{self.node_types_map.get(v, '?')}"
        
        type_pair_feat = np.zeros(len(self.type_pair_to_idx), dtype=np.float32)
        if tp_key in self.type_pair_to_idx:
            type_pair_feat[self.type_pair_to_idx[tp_key]] = 1.0
            
        return np.concatenate([feat_u, feat_v, np.abs(feat_u - feat_v), feat_u * feat_v, h, [same_type], type_pair_feat]).astype(np.float32)

    def predict_targets(self, source_uri: str, top_k: int = 5) -> List[Dict]:
        if not self.is_loaded or self.model is None or source_uri not in self.node_to_idx:
            return []
            
        logger.info(f"Calcul des prédictions pour {source_uri} avec {self.model_type}")

        candidates = [n for n in self.idx_to_node.values() if n != source_uri]
        if not candidates:
            return []
            
        heuristics_list = []
        src_idxs = []
        dst_idxs = []
        pair_features = []
        
        src_idx = self.node_to_idx[source_uri]
        
        for cand in candidates:
            h = self._compute_heuristics(source_uri, cand)
            heuristics_list.append(h)
            src_idxs.append(src_idx)
            dst_idxs.append(self.node_to_idx[cand])
            
            if self.model_type in ["MLP", "XGBOOST", "SKLEARN"]:
                pair_features.append(self._build_pair_features(source_uri, cand, h))
                
        preds = []
        
        if self.model_type in ["GCN", "GraphSAGE"]:
            H_cand = torch.tensor(heuristics_list, dtype=torch.float32).to(DEVICE)
            src_t = torch.tensor(src_idxs, dtype=torch.long).to(DEVICE)
            dst_t = torch.tensor(dst_idxs, dtype=torch.long).to(DEVICE)
            with torch.no_grad():
                preds = torch.sigmoid(self.model(self.X_nodes, self.adj_norm, src_t, dst_t, H_cand)).cpu().numpy()
        else:
            X_cand = np.array(pair_features)
            # Ajustement dynamique des dimensions si nécessaire
            expected_dim = None
            if hasattr(self.model, "n_features_in_"):
                expected_dim = self.model.n_features_in_
            elif hasattr(self.model, "num_features"):
                expected_dim = self.model.num_features()
            
            if expected_dim is not None and X_cand.shape[1] != expected_dim:
                logger.warning(f"Feature dimension mismatch: got {X_cand.shape[1]}, expected {expected_dim}. Adjusting...")
                if X_cand.shape[1] > expected_dim:
                    X_cand = X_cand[:, :expected_dim]
                else:
                    padding = np.zeros((X_cand.shape[0], expected_dim - X_cand.shape[1]), dtype=np.float32)
                    X_cand = np.hstack([X_cand, padding])
                    
            if self.model_type == "MLP":
                X_cand_t = torch.tensor(X_cand, dtype=torch.float32).to(DEVICE)
                with torch.no_grad():
                    preds = torch.sigmoid(self.model(X_cand_t)).cpu().numpy()
            elif self.model_type == "SKLEARN":
                preds = self.model.predict_proba(X_cand)[:, 1]
            elif self.model_type == "XGBOOST":
                import xgboost as xgb
                dmatrix = xgb.DMatrix(X_cand)
                preds = self.model.predict(dmatrix)

        results = []
        for i, cand in enumerate(candidates):
            results.append({
                "target_uri": cand,
                "probability": float(preds[i])
            })
            
        results.sort(key=lambda x: x["probability"], reverse=True)
        return results[:top_k]

# Instance singleton
ml_service = MLPredictorService()
