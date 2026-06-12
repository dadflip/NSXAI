# -*- coding: utf-8 -*-
"""
pipeline.py
===========
Neuro-Symbolic Link Prediction Pipeline — Tasks 2, 3 & 4.

Refactored for:
  - Full framework agnosticism (PyTorch optional, XGBoost optional)
  - Zero global mutable state (all config in PipelineConfig dataclass)
  - Clean separation of concerns across modules/classes
  - Correct cold-start inference (self.classifier, not self.model)
  - Single bundle write path (no double-save)
  - Typed interfaces throughout

Overview
--------
Task 2 — Multi-seed neural link prediction
    Logistic Regression, Random Forest, XGBoost, MLP, GCN, GraphSAGE
    across N seeds → aggregated probability + optional numeric boost.

Task 3 — Neuro-symbolic filtering & ranking
    BFS path distance, PageRank bonus, symbolic confidence layer,
    adaptive neuro-symbolic fusion.

Task 4 — Explanation generation & deployment
    Structured NL explanations, Task4Bundle / NSXAIInferenceBundle,
    FastAPI endpoint (optional).

Usage
-----
    from pipeline import PipelineConfig, run_pipeline

    cfg = PipelineConfig(
        ontology_path   = "ontology_matrix.csv",
        output_dir      = "outputs",
        target_types    = ["GameElementResource"],
        source_label    = "topic",
        target_label    = "game element",
    )
    results = run_pipeline(cfg)

    # Or step by step:
    nodes, edges, num_df = load_ontology("ontology_matrix.csv", cfg)
    t2 = run_task2(nodes, edges, num_df, cfg)
    t3 = run_task3(t2, cfg)
    df4, bundle, paths = run_task4(t3["df_topk"], t3["G_sym"], cfg)
"""

# =============================================================================
# 0.  IMPORTS
# =============================================================================

from __future__ import annotations

import json
import logging
import os
import pickle
import random
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import matplotlib
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import seaborn as sns

# ── Optional heavy dependencies ───────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None  # type: ignore

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, f1_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("nsxai")

matplotlib.rcParams.update({
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
    "axes.grid":         True,
    "grid.color":        "#E8E8E8",
    "grid.linewidth":    0.6,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "font.family":       "DejaVu Sans",
    "font.size":         11,
})


# =============================================================================
# 1.  CONFIGURATION  (single source of truth — no module-level globals)
# =============================================================================

@dataclass
class NumericConfig:
    """All numeric OWL property settings."""
    properties: List[str] = field(default_factory=lambda: [
        "has_totalLikes",
        "has_totalDownloads",
        "has_TotalCompletionHours",
        "has_TotalEnrollment",
        "has_totalSites",
    ])
    weights: Dict[str, float] = field(default_factory=lambda: {
        "has_totalLikes":           0.30,
        "has_totalDownloads":       0.25,
        "has_TotalCompletionHours": 0.15,
        "has_TotalEnrollment":      0.10,
        "has_totalSites":           0.10,
    })
    normalize: bool = True
    score_boost_weight: float = 0.20   # share of numeric score in final ranking
    feature_weight: float = 2.0        # amplification factor for feature vectors


@dataclass
class SymbolicConfig:
    """Task 3 symbolic layer weights and thresholds."""
    w_base: float = 0.70   # ontological path distance component
    w_pr: float = 0.20     # PageRank bonus component
    w_bfs: float = 0.10    # BFS participation index component

    neural_weight_normal: float = 0.35
    symbolic_weight_normal: float = 0.65
    neural_weight_flat: float = 0.20
    symbolic_weight_flat: float = 0.80
    flat_ratio_threshold: float = 0.30

    bfs_max_paths: int = 3
    bfs_cutoff: int = 6
    bfs_max_pairs: Optional[int] = None  # None = all top-K pairs


@dataclass
class GNNConfig:
    """GNN training hyperparameters."""
    epochs: int = 250
    patience: int = 30
    lr: float = 0.005
    hidden_dim: int = 32
    embedding_dim: int = 16


@dataclass
class PipelineConfig:
    """
    Master configuration — pass this to every run_* function.

    All paths, labels, hyperparameters, and feature settings are
    consolidated here so no function relies on module-level globals.
    """
    # I/O
    ontology_path: str = "task1/ontology_matrix.csv"
    output_dir: str = "outputs/task2_multimodel"

    # Dataset
    target_types: List[str] = field(default_factory=lambda: ["GameElementResource"])
    negative_ratio: int = 2
    top_k: int = 5

    # Reproducibility
    seeds: List[int] = field(default_factory=lambda: [42, 43, 44, 45, 46])
    master_seed: int = 42

    # Graph / ontology
    meta_cols: Set[str] = field(default_factory=lambda: {"id", "label", "type"})
    struct_rels: Set[str] = field(
        default_factory=lambda: {"type", "subClassOf", "label", "domain", "range"}
    )

    # Feature configs
    numeric: NumericConfig = field(default_factory=NumericConfig)
    symbolic: SymbolicConfig = field(default_factory=SymbolicConfig)
    gnn: GNNConfig = field(default_factory=GNNConfig)

    # Task 4 labels
    source_label: str = "source"
    target_label: str = "target"

    # Explanation thresholds
    conf_high: float = 0.80
    conf_moderate: float = 0.40
    score_high: float = 0.80
    score_moderate: float = 0.45

    # Computed device (set post-init)
    device: str = field(init=False)

    def __post_init__(self) -> None:
        if HAS_TORCH and torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def t3_dir(self) -> str:
        p = os.path.join(self.output_dir, "task3")
        os.makedirs(p, exist_ok=True)
        return p

    @property
    def t4_dir(self) -> str:
        p = os.path.join(self.output_dir, "task4")
        os.makedirs(p, exist_ok=True)
        return p


# Required columns from Task 3 output
REQUIRED_T3_COLS = frozenset({
    "source", "target",
    "probability_mean", "symbolic_confidence", "neurosymbolic_score",
    "known_positive",
})

# Ordered output columns for Task 4 exports
OUTPUT_COLS = [
    "source", "target",
    "probability_mean", "symbolic_confidence", "neurosymbolic_score",
    "confidence_label", "path_distance", "key_relation",
    "ontology_path", "known_positive",
    "explanation", "explanation_blocks",
]

MODEL_COLORS = {
    "Logistic Regression":        "#5B8DEF",
    "Random Forest":              "#F4A44A",
    "MLP Link Predictor":         "#A07BE5",
    "GCN Link Prediction":        "#3EC97C",
    "GraphSAGE Link Prediction":  "#EF6B5B",
    "XGBoost":                    "#2EC4B6",
}

METRICS = ["roc_auc", "average_precision", "accuracy", "f1"]


# =============================================================================
# 2.  GENERAL UTILITIES
# =============================================================================

def shorten(uri: str) -> str:
    """Extract the local name from a URI or slash/hash-delimited string."""
    if not isinstance(uri, str):
        return str(uri)
    parts = re.split(r"[#/]", uri.strip())
    return next((p for p in reversed(parts) if p), uri)


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert *val* to float, returning *default* on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def conf_label(conf: float, cfg: PipelineConfig) -> str:
    """Map symbolic confidence to a human-readable category label."""
    if conf >= cfg.conf_high:
        return "High"
    if conf >= cfg.conf_moderate:
        return "Moderate"
    return "Weak"


def set_seed(seed: int) -> None:
    """Set all RNGs to a fixed seed (Python, NumPy, PyTorch if available)."""
    random.seed(seed)
    np.random.seed(seed)
    if HAS_TORCH:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)


def _to_device(tensor, device: str):
    """Move a torch tensor to device (no-op if torch unavailable)."""
    if HAS_TORCH and isinstance(tensor, torch.Tensor):
        return tensor.to(device)
    return tensor


# =============================================================================
# 3.  DATA LOADING & PARSING
# =============================================================================

def load_ontology(
    path: str,
    cfg: PipelineConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load and parse an ontology matrix CSV.

    Returns
    -------
    nodes_df       : DataFrame with columns [id, label, type]
    edges_df       : DataFrame with columns [source, relation, target]
    numeric_raw_df : DataFrame indexed by node id with numeric property columns
    """
    df = pd.read_csv(path)

    node_info: Dict[str, dict] = {}
    for _, row in df.iterrows():
        if pd.isna(row.get("id")):
            continue
        sid = shorten(str(row["id"]).strip())
        node_info[sid] = {
            "label": str(row["label"]).strip() if pd.notna(row.get("label")) else sid,
            "type":  shorten(str(row["type"]).strip()) if pd.notna(row.get("type")) else "unknown",
        }

    entities: Set[str] = set(node_info)
    edge_records: List[dict] = []
    relation_cols = [c for c in df.columns if c not in cfg.meta_cols]
    num_props = cfg.numeric.properties

    present_numeric = [c for c in num_props if c in df.columns]
    missing_numeric = [c for c in num_props if c not in df.columns]
    if missing_numeric:
        log.info("Numeric columns absent from CSV (ignored): %s", missing_numeric)

    numeric_records: Dict[str, dict] = {}
    for _, row in df.iterrows():
        if pd.isna(row.get("id")):
            continue
        sid = shorten(str(row["id"]).strip())
        rec: Dict[str, float] = {}
        for col in present_numeric:
            val = row.get(col, np.nan)
            try:
                rec[col] = float(val) if pd.notna(val) else np.nan
            except (ValueError, TypeError):
                rec[col] = np.nan
        numeric_records[sid] = rec

    for _, row in df.iterrows():
        if pd.isna(row.get("id")):
            continue
        s = shorten(str(row["id"]).strip())
        for rel in relation_cols:
            if pd.isna(row.get(rel)):
                continue
            for o_raw in map(str.strip, str(row[rel]).split("|")):
                if not o_raw or o_raw.lower() == "nan":
                    continue
                try:
                    float(o_raw)   # numeric data property → skip
                except ValueError:
                    o = shorten(o_raw)
                    edge_records.append({"source": s, "relation": rel, "target": o})
                    entities.add(o)

    nodes_df = pd.DataFrame([
        {"id": e, **node_info.get(e, {"label": e, "type": "unknown"})}
        for e in entities
    ])
    edges_df = pd.DataFrame(edge_records).drop_duplicates() if edge_records else pd.DataFrame(
        columns=["source", "relation", "target"]
    )
    numeric_raw_df = pd.DataFrame.from_dict(
        numeric_records, orient="index",
        columns=present_numeric if present_numeric else [],
    ).reindex(list(entities))

    log.info(
        "Ontology loaded: %d nodes, %d edges, %d numeric properties.",
        len(nodes_df), len(edges_df), len(present_numeric),
    )
    return nodes_df, edges_df, numeric_raw_df


# =============================================================================
# 4.  NUMERIC NODE SCORES
# =============================================================================

def build_numeric_node_scores(
    numeric_raw_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> Dict[str, float]:
    """
    Compute a scalar aggregated numeric score ∈ [0,1] for every node.

    Steps: NaN→0, optional min-max per column, weighted sum, final rescale.
    """
    num_cfg = cfg.numeric
    if numeric_raw_df.empty or len(numeric_raw_df.columns) == 0:
        return {node: 0.0 for node in numeric_raw_df.index}

    df = numeric_raw_df.copy().fillna(0.0)

    if num_cfg.normalize:
        for col in df.columns:
            lo, hi = df[col].min(), df[col].max()
            df[col] = (df[col] - lo) / (hi - lo) if hi > lo else 0.0

    active = [c for c in df.columns if c in num_cfg.weights]
    if not active:
        return {node: 0.0 for node in df.index}

    total_w = sum(num_cfg.weights[c] for c in active)
    if total_w == 0:
        return {node: 0.0 for node in df.index}

    score_series = sum(df[c] * (num_cfg.weights[c] / total_w) for c in active)
    s_max = score_series.max()
    if s_max > 0:
        score_series /= s_max

    return score_series.to_dict()


# =============================================================================
# 5.  DATASET CONSTRUCTION
# =============================================================================

def _expand_target_types(edges_df: pd.DataFrame, base_types: List[str]) -> Set[str]:
    """Expand target types via subClassOf edges."""
    T: Set[str] = set(base_types)
    while True:
        nxt = set(
            edges_df.loc[
                (edges_df["relation"] == "subClassOf") & edges_df["target"].isin(T),
                "source",
            ]
        )
        if nxt <= T:
            break
        T |= nxt
    return T


def build_dataset(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Set[Tuple], Set[str]]:
    """
    Build binary link-prediction dataset.

    Returns (pos_df, neg_df, dataset, pos_set, target_node_ids)
    """
    T = _expand_target_types(edges_df, cfg.target_types)
    N = set(nodes_df.loc[nodes_df["type"].isin(T), "id"])

    multi_pos: Dict[str, Set] = defaultdict(set)
    for row in edges_df.itertuples(index=False):
        if row.target in N and row.relation not in cfg.struct_rels:
            multi_pos[row.source].add(row.target)

    pos_df = pd.DataFrame(
        [{"source": s, "target": t, "label": 1}
         for s, ts in multi_pos.items() for t in ts]
    )
    pos_set = set(zip(pos_df["source"], pos_df["target"]))

    rng      = random.Random(cfg.master_seed)
    src_pool = nodes_df["id"].values
    tgt_pool = list(N)
    neg_pairs: Set[Tuple] = set()
    target_count = len(pos_df) * cfg.negative_ratio
    while len(neg_pairs) < target_count:
        s, t = rng.choice(src_pool), rng.choice(tgt_pool)
        if s != t and (s, t) not in pos_set:
            neg_pairs.add((s, t))

    neg_df = pd.DataFrame(list(neg_pairs), columns=["source", "target"])
    neg_df["label"] = 0

    dataset = (
        pd.concat([pos_df, neg_df], ignore_index=True)
        .sample(frac=1, random_state=cfg.master_seed)
        .reset_index(drop=True)
    )

    log.info(
        "Dataset: %d pos, %d neg (%d:1). Target types: %d nodes.",
        len(pos_df), len(neg_df), cfg.negative_ratio, len(N),
    )
    return pos_df, neg_df, dataset, pos_set, N


# =============================================================================
# 6.  GRAPH CONSTRUCTION
# =============================================================================

def build_graph(
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    exclude_pairs: Optional[Set] = None,
) -> nx.DiGraph:
    """Build directed NetworkX graph from node/edge tables."""
    G = nx.DiGraph()
    node_set = set(nodes_df["id"])

    for _, row in nodes_df.iterrows():
        G.add_node(row["id"], label=row["label"], type=row.get("type", "unknown"))

    for _, row in edges_df.iterrows():
        src, tgt = str(row["source"]), str(row["target"])
        if src not in node_set or tgt not in node_set:
            continue
        if exclude_pairs and (src, tgt) in exclude_pairs:
            continue
        G.add_edge(src, tgt, relation=str(row["relation"]).strip())

    return G


# =============================================================================
# 7.  NODE FEATURES
# =============================================================================

def _build_node_numeric_matrix(
    node_ids: List[str],
    numeric_raw_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> np.ndarray:
    """
    Build (num_nodes × len(NUMERIC_PROPERTIES)) weighted numeric feature matrix.
    Absent columns are filled with zeros.
    """
    num_cfg = cfg.numeric
    n, k = len(node_ids), len(num_cfg.properties)
    mat = np.zeros((n, k), dtype=np.float32)

    for ci, prop in enumerate(num_cfg.properties):
        if prop not in numeric_raw_df.columns:
            continue
        raw_w = num_cfg.weights.get(prop, 1.0)
        col_vals = (
            numeric_raw_df[prop].reindex(node_ids).fillna(0.0).values.astype(np.float32)
        )
        lo, hi = col_vals.min(), col_vals.max()
        if hi > lo:
            col_vals = (col_vals - lo) / (hi - lo)
        mat[:, ci] = col_vals * raw_w * num_cfg.feature_weight

    return mat


def build_node_features(
    G_mp: nx.DiGraph,
    nodes: pd.DataFrame,
    numeric_raw_df: pd.DataFrame,
    pagerank: Dict[str, float],
    cfg: PipelineConfig,
) -> dict:
    """
    Build node feature matrix and associated metadata.

    Returns a dict with keys:
        node_ids, node_to_idx, idx_to_node,
        X_nodes (tensor or ndarray), X_nodes_np,
        numeric_bias_tensor, numeric_feat_matrix,
        type_map, node_types
    """
    node_ids    = list(G_mp.nodes())
    node_to_idx = {n: i for i, n in enumerate(node_ids)}
    idx_to_node = {i: n for n, i in node_to_idx.items()}

    deg_centrality = nx.degree_centrality(G_mp)
    type_map       = dict(zip(nodes["id"], nodes["type"]))
    node_types     = sorted(nodes["type"].unique())

    numeric_feat_matrix = _build_node_numeric_matrix(node_ids, numeric_raw_df, cfg)

    feature_rows = []
    for node in node_ids:
        ntype = type_map.get(node, "unknown")
        row = {
            "in_degree":         G_mp.in_degree(node),
            "out_degree":        G_mp.out_degree(node),
            "degree_centrality": deg_centrality.get(node, 0.0),
            "pagerank_context":  pagerank.get(node, 0.0),
        }
        for t in node_types:
            row[f"type_{t}"] = 1.0 if ntype == t else 0.0
        feature_rows.append(row)

    feat_df = pd.DataFrame(feature_rows, index=node_ids)
    scale_cols = ["in_degree", "out_degree", "degree_centrality", "pagerank_context"]
    feat_df[scale_cols] = StandardScaler().fit_transform(feat_df[scale_cols])

    X_nodes_np = np.concatenate(
        [feat_df.values.astype(np.float32), numeric_feat_matrix], axis=1
    )

    if HAS_TORCH:
        X_nodes = torch.tensor(X_nodes_np, dtype=torch.float32)
        X_nodes = _to_device(X_nodes, cfg.device)
    else:
        X_nodes = X_nodes_np

    numeric_scores = build_numeric_node_scores(numeric_raw_df, cfg)
    numeric_bias_np = np.array(
        [numeric_scores.get(n, 0.0) for n in node_ids], dtype=np.float32
    ).reshape(-1, 1)

    if HAS_TORCH:
        numeric_bias_tensor = _to_device(
            torch.tensor(numeric_bias_np, dtype=torch.float32), cfg.device
        )
    else:
        numeric_bias_tensor = numeric_bias_np

    log.info(
        "Node features: shape=%s (%d numeric dims).",
        X_nodes_np.shape, len(cfg.numeric.properties),
    )
    return dict(
        node_ids=node_ids,
        node_to_idx=node_to_idx,
        idx_to_node=idx_to_node,
        X_nodes=X_nodes,
        X_nodes_np=X_nodes_np,
        numeric_bias_tensor=numeric_bias_tensor,
        numeric_feat_matrix=numeric_feat_matrix,
        type_map=type_map,
        node_types=node_types,
    )


# =============================================================================
# 8.  ADJACENCY MATRIX
# =============================================================================

def build_adjacency(
    node_ids: List[str],
    node_to_idx: Dict[str, int],
    G_mp: nx.DiGraph,
    cfg: PipelineConfig,
):
    """Build symmetrised, self-looped, row-normalised adjacency (D^{-1}(A+I))."""
    n = len(node_ids)
    if HAS_TORCH:
        adj = torch.zeros((n, n), dtype=torch.float32)
        for u, v in G_mp.edges():
            if u in node_to_idx and v in node_to_idx:
                i, j = node_to_idx[u], node_to_idx[v]
                adj[i, j] = adj[j, i] = 1.0
        adj += torch.eye(n)
        adj_norm = adj / adj.sum(dim=1, keepdim=True).clamp(min=1.0)
        return _to_device(adj_norm, cfg.device)
    else:
        adj = np.zeros((n, n), dtype=np.float32)
        for u, v in G_mp.edges():
            if u in node_to_idx and v in node_to_idx:
                i, j = node_to_idx[u], node_to_idx[v]
                adj[i, j] = adj[j, i] = 1.0
        np.fill_diagonal(adj, 1.0)
        row_sums = adj.sum(axis=1, keepdims=True).clip(min=1.0)
        return adj / row_sums


# =============================================================================
# 9.  GRAPH HEURISTICS & PAIR FEATURES
# =============================================================================

class GraphHeuristics:
    """
    10-dimensional graph-structural heuristic vector per (u, v) pair.

    Heuristics (index 0–9):
        Adamic-Adar, Jaccard, Preferential Attachment, Common Neighbours,
        Shortest Path, 2nd-order Common Neighbours, Resource Allocation,
        Clustering(u), Clustering(v), |PageRank(u)−PageRank(v)|
    """

    def __init__(self, G_mp: nx.DiGraph, pagerank: Dict[str, float]):
        self._G  = G_mp.to_undirected()
        self._pr = pagerank
        self._cc: Optional[dict] = None

    def _clustering(self) -> dict:
        if self._cc is None:
            self._cc = nx.clustering(self._G)
        return self._cc

    def compute(self, u: str, v: str) -> np.ndarray:
        if u not in self._G or v not in self._G:
            return np.zeros(10, dtype=np.float32)

        def safe(fn):
            try:
                return fn()
            except Exception:
                return 0.0

        aa  = safe(lambda: next(nx.adamic_adar_index(self._G,       [(u, v)]))[2])
        jc  = safe(lambda: next(nx.jaccard_coefficient(self._G,     [(u, v)]))[2])
        pa  = safe(lambda: next(nx.preferential_attachment(self._G, [(u, v)]))[2])
        cn  = safe(lambda: len(list(nx.common_neighbors(self._G, u, v))))
        sp  = safe(lambda: nx.shortest_path_length(self._G, u, v)) or 999
        ra  = safe(lambda: next(nx.resource_allocation_index(self._G, [(u, v)]))[2])

        nb_u = set(self._G.neighbors(u))
        nb_v = set(self._G.neighbors(v))
        n2_u = {n for nb in nb_u for n in self._G.neighbors(nb)} - {u}
        n2_v = {n for nb in nb_v for n in self._G.neighbors(nb)} - {v}
        cn2  = len(n2_u & n2_v)

        cc      = self._clustering()
        pr_diff = abs(self._pr.get(u, 0.0) - self._pr.get(v, 0.0))

        return np.array(
            [aa, jc, pa, cn, sp, cn2, ra, cc.get(u, 0.0), cc.get(v, 0.0), pr_diff],
            dtype=np.float32,
        )

    def batch(self, df: pd.DataFrame) -> np.ndarray:
        return np.vstack([
            self.compute(r["source"], r["target"])
            for _, r in df.iterrows()
        ]).astype(np.float32)


def _build_numeric_pair_features(
    u: str,
    v: str,
    numeric_scores: Dict[str, float],
    numeric_feat_matrix: np.ndarray,
    node_to_idx: Dict[str, int],
    cfg: PipelineConfig,
) -> np.ndarray:
    """Numeric sub-vector for pair (u, v): [5 aggregate + 2K per-property]."""
    K       = len(cfg.numeric.properties)
    score_u = numeric_scores.get(u, 0.0)
    score_v = numeric_scores.get(v, 0.0)

    pp_v = (
        numeric_feat_matrix[node_to_idx[v]].astype(np.float32)
        if K > 0 and v in node_to_idx else np.zeros(K, dtype=np.float32)
    )
    pp_u = (
        numeric_feat_matrix[node_to_idx[u]].astype(np.float32)
        if K > 0 and u in node_to_idx else np.zeros(K, dtype=np.float32)
    )

    base = np.array([
        score_v, score_u,
        abs(score_v - score_u),
        score_v * score_u,
        float(np.max(pp_v)) if K > 0 else 0.0,
    ], dtype=np.float32)

    return np.concatenate([base, pp_v, pp_u]) * cfg.numeric.feature_weight


def build_pair_features(
    df: pd.DataFrame,
    X_nodes_np: np.ndarray,
    node_to_idx: Dict[str, int],
    pagerank: Dict[str, float],
    type_map: Dict[str, str],
    heuristics: GraphHeuristics,
    numeric_scores: Dict[str, float],
    numeric_feat_matrix: np.ndarray,
    cfg: PipelineConfig,
) -> np.ndarray:
    """Full pair feature vector per row: [src|dst|diff|prod|heur|pr|type|numeric]."""
    rows = []
    for _, r in df.iterrows():
        u, v = r["source"], r["target"]
        if u not in node_to_idx or v not in node_to_idx:
            continue
        sf   = X_nodes_np[node_to_idx[u]]
        df_  = X_nodes_np[node_to_idx[v]]
        h    = heuristics.compute(u, v)
        pu, pv = float(pagerank.get(u, 0.0)), float(pagerank.get(v, 0.0))
        nf   = _build_numeric_pair_features(
            u, v, numeric_scores, numeric_feat_matrix, node_to_idx, cfg
        )
        rows.append(np.concatenate([
            sf, df_,
            np.abs(sf - df_),
            sf * df_,
            h,
            np.array([pu, pv, abs(pu - pv)], dtype=np.float32),
            np.array([float(type_map.get(u, "?") == type_map.get(v, "!"))], dtype=np.float32),
            nf,
        ]))
    if not rows:
        return np.empty((0, 0), dtype=np.float32)
    return np.vstack(rows).astype(np.float32)


# =============================================================================
# 10.  PYTORCH MODELS  (only defined when torch available)
# =============================================================================

if HAS_TORCH:
    class LinkDecoder(nn.Module):
        """MLP decoder: [z_src|z_dst|diff|prod|heur|pr_src|pr_dst|num_bias] → logit."""

        def __init__(self, embedding_dim: int = 16, heuristic_dim: int = 10, hidden_dim: int = 64):
            super().__init__()
            input_dim = embedding_dim * 4 + heuristic_dim + 2 + 1
            self.mlp = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim, 1),
            )

        def forward(self, z_src, z_dst, heur, pr_src, pr_dst, num_bias_dst):
            for t in (pr_src, pr_dst, num_bias_dst):
                pass  # handled below
            if pr_src.dim() == 1:     pr_src = pr_src.unsqueeze(-1)
            if pr_dst.dim() == 1:     pr_dst = pr_dst.unsqueeze(-1)
            if num_bias_dst.dim() == 1: num_bias_dst = num_bias_dst.unsqueeze(-1)
            x = torch.cat(
                [z_src, z_dst, torch.abs(z_src - z_dst), z_src * z_dst,
                 heur, pr_src, pr_dst, num_bias_dst], dim=1
            )
            return self.mlp(x).squeeze(-1)

    class GCNLayer(nn.Module):
        def __init__(self, in_dim: int, out_dim: int):
            super().__init__()
            self.linear = nn.Linear(in_dim, out_dim)

        def forward(self, x, adj_norm, importance=None):
            if importance is not None:
                x = x * importance
            return F.relu(self.linear(torch.matmul(adj_norm, x)))

    class GCNLinkPredictionModel(nn.Module):
        def __init__(self, in_dim: int, cfg: PipelineConfig):
            super().__init__()
            h, e = cfg.gnn.hidden_dim, cfg.gnn.embedding_dim
            self.enc1    = GCNLayer(in_dim, h)
            self.enc2    = GCNLayer(h, e)
            self.decoder = LinkDecoder(e)
            self.register_buffer("node_pr",       torch.zeros(1, 1))
            self.register_buffer("node_num_bias", torch.zeros(1, 1))
            self._boost  = cfg.numeric.score_boost_weight

        def init_buffers(self, pagerank, node_ids, numeric_bias_tensor):
            pr_vals = torch.tensor([pagerank.get(n, 0.0) for n in node_ids], dtype=torch.float32).view(-1, 1)
            self.register_buffer("node_pr",       pr_vals)
            self.register_buffer("node_num_bias", numeric_bias_tensor.clone())

        def forward(self, x, adj_norm, src_idx, dst_idx, heuristics):
            scale = 1.0 + self.node_num_bias * self._boost
            h = self.enc1(x * scale, adj_norm, self.node_pr)
            z = self.enc2(h * scale, adj_norm, self.node_pr)
            return self.decoder(
                z[src_idx], z[dst_idx], heuristics,
                self.node_pr[src_idx], self.node_pr[dst_idx],
                self.node_num_bias[dst_idx],
            )

    class GraphSAGELayer(nn.Module):
        def __init__(self, in_dim: int, out_dim: int):
            super().__init__()
            self.self_l  = nn.Linear(in_dim, out_dim)
            self.neigh_l = nn.Linear(in_dim, out_dim)

        def forward(self, x, adj_norm):
            return F.relu(self.self_l(x) + self.neigh_l(torch.matmul(adj_norm, x)))

    class GraphSAGEEncoder(nn.Module):
        def __init__(self, in_dim, hidden_dim=32, embedding_dim=16, dropout=0.5):
            super().__init__()
            self.l1 = GraphSAGELayer(in_dim, hidden_dim)
            self.l2 = GraphSAGELayer(hidden_dim, embedding_dim)
            self.do = nn.Dropout(dropout)

        def forward(self, x, adj_norm):
            return self.l2(self.do(self.l1(x, adj_norm)), adj_norm)

    class GraphSAGELinkPredictionModel(nn.Module):
        def __init__(self, in_dim: int, cfg: PipelineConfig):
            super().__init__()
            h, e = cfg.gnn.hidden_dim, cfg.gnn.embedding_dim
            self.encoder = GraphSAGEEncoder(in_dim, h, e)
            self.decoder = LinkDecoder(e)
            self.register_buffer("node_pr",       torch.zeros(1, 1))
            self.register_buffer("node_num_bias", torch.zeros(1, 1))
            self._boost  = cfg.numeric.score_boost_weight

        def init_buffers(self, pagerank, node_ids, numeric_bias_tensor):
            pr_vals = torch.tensor([pagerank.get(n, 0.0) for n in node_ids], dtype=torch.float32).view(-1, 1)
            self.register_buffer("node_pr",       pr_vals)
            self.register_buffer("node_num_bias", numeric_bias_tensor.clone())

        def forward(self, x, adj_norm, src_idx, dst_idx, heuristics):
            scale = 1.0 + self.node_num_bias * self._boost
            z = self.encoder(x * scale, adj_norm)
            return self.decoder(
                z[src_idx], z[dst_idx], heuristics,
                self.node_pr[src_idx], self.node_pr[dst_idx],
                self.node_num_bias[dst_idx],
            )

    class PairMLP(nn.Module):
        def __init__(self, input_dim: int, hidden_dim: int = 128):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, 1),
            )

        def forward(self, x):
            return self.net(x).squeeze(-1)


# =============================================================================
# 11.  TRAINING & EVALUATION
# =============================================================================

def evaluate_predictions(
    model_name: str,
    y_true,
    y_prob,
    threshold: float = 0.5,
) -> dict:
    """Return dict of standard binary classification metrics."""
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    return {
        "model":             model_name,
        "roc_auc":           float(roc_auc_score(y_true, y_prob)),
        "average_precision": float(average_precision_score(y_true, y_prob)),
        "accuracy":          float(accuracy_score(y_true, y_pred)),
        "f1":                float(f1_score(y_true, y_pred, zero_division=0)),
    }


def _df_to_link_tensors(df: pd.DataFrame, node_to_idx: Dict[str, int], device: str):
    """Convert pair DataFrame to (src_idx, dst_idx, labels) torch tensors."""
    if not HAS_TORCH:
        raise RuntimeError("PyTorch is required for GNN training.")
    src = torch.tensor([node_to_idx[n] for n in df["source"]], dtype=torch.long)
    dst = torch.tensor([node_to_idx[n] for n in df["target"]], dtype=torch.long)
    y   = torch.tensor(df["label"].values, dtype=torch.float32)
    return _to_device(src, device), _to_device(dst, device), _to_device(y, device)


def _train_gnn(
    model,
    name: str,
    splits: dict,
    X_nodes,
    adj_norm,
    cfg: PipelineConfig,
) -> np.ndarray:
    """
    Train a GNN with early stopping. Returns test-set probabilities.

    splits keys: train_src/dst/y, val_src/dst/y_np, test_src/dst, H_train/val/test
    """
    gc = cfg.gnn
    opt  = torch.optim.Adam(model.parameters(), lr=gc.lr, weight_decay=1e-3)
    crit = nn.BCEWithLogitsLoss()
    best_auc, best_state, patience_cnt = -1.0, None, 0

    for epoch in range(1, gc.epochs + 1):
        model.train()
        opt.zero_grad()
        loss = crit(
            model(X_nodes, adj_norm, splits["train_src"], splits["train_dst"], splits["H_train"]),
            splits["train_y"],
        )
        loss.backward()
        opt.step()

        model.eval()
        with torch.no_grad():
            val_prob = torch.sigmoid(
                model(X_nodes, adj_norm, splits["val_src"], splits["val_dst"], splits["H_val"])
            ).cpu().numpy()
        val_auc = roc_auc_score(splits["val_y_np"], val_prob)

        if val_auc > best_auc:
            best_auc    = val_auc
            best_state  = {k: v.clone() for k, v in model.state_dict().items()}
            patience_cnt = 0
        else:
            patience_cnt += 1

        if epoch % 50 == 0:
            log.info("[%s] epoch=%03d loss=%.4f val_auc=%.4f", name, epoch, loss.item(), val_auc)
        if patience_cnt >= gc.patience:
            log.info("[%s] Early stop at epoch %d.", name, epoch)
            break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        return torch.sigmoid(
            model(X_nodes, adj_norm, splits["test_src"], splits["test_dst"], splits["H_test"])
        ).cpu().numpy()


def _train_mlp(
    X_train_t, X_val_t, X_test_t, y_train, y_val, cfg: PipelineConfig
) -> Tuple[Any, np.ndarray]:
    """Train PairMLP; returns (model, test_probs)."""
    model = PairMLP(input_dim=X_train_t.shape[1]).to(cfg.device)
    opt   = torch.optim.Adam(model.parameters(), lr=5e-4, weight_decay=1e-4)
    crit  = nn.BCEWithLogitsLoss()
    y_t   = _to_device(torch.tensor(y_train, dtype=torch.float32), cfg.device)
    best_auc, best_state, patience_cnt = -1.0, None, 0

    for epoch in range(1, cfg.gnn.epochs + 1):
        model.train()
        opt.zero_grad()
        crit(model(X_train_t), y_t).backward()
        opt.step()
        model.eval()
        with torch.no_grad():
            vp = torch.sigmoid(model(X_val_t)).cpu().numpy()
        vauc = roc_auc_score(y_val, vp)
        if vauc > best_auc:
            best_auc    = vauc
            best_state  = {k: v.clone() for k, v in model.state_dict().items()}
            patience_cnt = 0
        else:
            patience_cnt += 1
        if patience_cnt >= cfg.gnn.patience:
            break

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        test_probs = torch.sigmoid(model(X_test_t)).cpu().numpy()
    return model, test_probs


# =============================================================================
# 12.  NUMERIC RANKING BOOST
# =============================================================================

def _apply_numeric_boost(
    df: pd.DataFrame,
    numeric_scores: Dict[str, float],
    cfg: PipelineConfig,
) -> pd.Series:
    """
    Blend model probability with target numeric score:
        final = (1-w)*prob + w*numeric_score_target
    """
    w = cfg.numeric.score_boost_weight
    if w == 0.0:
        return df["probability_mean"]
    prob_col   = "probability_mean" if "probability_mean" in df.columns else "probability"
    num_scores = df["target"].map(lambda t: numeric_scores.get(t, 0.0))
    return (1.0 - w) * df[prob_col] + w * num_scores


# =============================================================================
# 13.  SINGLE SEED TRAINING
# =============================================================================

def _score_candidates(
    model_name: str,
    model,
    cand_df: pd.DataFrame,
    H_cand,
    X_nodes,
    adj_norm,
    node_to_idx: Dict[str, int],
    pair_feat_fn: Callable,
    cfg: PipelineConfig,
) -> np.ndarray:
    """Dispatch inference to the right model type."""
    if model_name in ("Logistic Regression", "Random Forest", "XGBoost"):
        return model.predict_proba(pair_feat_fn(cand_df))[:, 1]

    if model_name == "MLP Link Predictor":
        xt = _to_device(
            torch.tensor(pair_feat_fn(cand_df), dtype=torch.float32), cfg.device
        )
        model.eval()
        with torch.no_grad():
            return torch.sigmoid(model(xt)).cpu().numpy()

    # GCN / GraphSAGE
    csrc = _to_device(
        torch.tensor([node_to_idx[n] for n in cand_df["source"]], dtype=torch.long), cfg.device
    )
    cdst = _to_device(
        torch.tensor([node_to_idx[n] for n in cand_df["target"]], dtype=torch.long), cfg.device
    )
    model.eval()
    with torch.no_grad():
        return torch.sigmoid(model(X_nodes, adj_norm, csrc, cdst, H_cand)).cpu().numpy()


def run_one_seed(
    seed: int,
    shared: dict,
    cfg: PipelineConfig,
) -> Tuple[List[dict], pd.DataFrame]:
    """
    Train all models for one seed; return (metrics_list, candidate_df).

    shared keys (read-only, pre-computed once):
        dataset, nodes, pos_set, N,
        X_nodes, X_nodes_np, adj_norm, node_to_idx, node_ids,
        numeric_scores, heuristics, numeric_feat_matrix,
        pagerank, type_map, context_dim, numeric_bias_tensor
    """
    log.info("=" * 50 + " SEED %d", seed)
    set_seed(seed)

    dataset    = shared["dataset"]
    node_to_idx = shared["node_to_idx"]
    X_nodes    = shared["X_nodes"]
    X_nodes_np = shared["X_nodes_np"]
    adj_norm   = shared["adj_norm"]
    pagerank   = shared["pagerank"]
    type_map   = shared["type_map"]
    heuristics = shared["heuristics"]
    num_scores = shared["numeric_scores"]
    num_fmat   = shared["numeric_feat_matrix"]
    num_bias   = shared["numeric_bias_tensor"]
    node_ids   = shared["node_ids"]
    N          = shared["N"]
    pos_set    = shared["pos_set"]
    nodes      = shared["nodes"]

    def pf(df):
        return build_pair_features(
            df, X_nodes_np, node_to_idx, pagerank,
            type_map, heuristics, num_scores, num_fmat, cfg,
        )

    # ── Splits ────────────────────────────────────────────────────────────────
    train_df, tmp  = train_test_split(dataset, test_size=0.30, random_state=seed)
    val_df, test_df = train_test_split(tmp,     test_size=0.50, random_state=seed)

    y_train = train_df["label"].values
    y_val   = val_df["label"].values
    y_test  = test_df["label"].values

    X_tr  = pf(train_df)
    X_val = pf(val_df)
    X_te  = pf(test_df)

    results  = []
    models   = {}
    global_state = shared["global_state"]

    # ── Logistic Regression ───────────────────────────────────────────────────
    lr = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)
    lr.fit(X_tr, y_train)
    lr_prob = lr.predict_proba(X_te)[:, 1]
    results.append(evaluate_predictions("Logistic Regression", y_test, lr_prob))
    models["Logistic Regression"] = lr

    # ── Random Forest ─────────────────────────────────────────────────────────
    rf = RandomForestClassifier(n_estimators=300, max_depth=8, class_weight="balanced", random_state=seed)
    rf.fit(X_tr, y_train)
    rf_prob = rf.predict_proba(X_te)[:, 1]
    results.append(evaluate_predictions("Random Forest", y_test, rf_prob))
    models["Random Forest"] = rf

    # ── XGBoost ───────────────────────────────────────────────────────────────
    if HAS_XGB:
        xgb = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                             random_state=seed, eval_metric="auc", verbosity=0)
        xgb.fit(X_tr, y_train)
        xgb_prob = xgb.predict_proba(X_te)[:, 1]
        results.append(evaluate_predictions("XGBoost", y_test, xgb_prob))
        models["XGBoost"] = xgb

    # ── MLP (requires torch) ──────────────────────────────────────────────────
    if HAS_TORCH:
        X_tr_t  = _to_device(torch.tensor(X_tr,  dtype=torch.float32), cfg.device)
        X_val_t = _to_device(torch.tensor(X_val, dtype=torch.float32), cfg.device)
        X_te_t  = _to_device(torch.tensor(X_te,  dtype=torch.float32), cfg.device)
        mlp, mlp_prob = _train_mlp(X_tr_t, X_val_t, X_te_t, y_train, y_val, cfg)
        results.append(evaluate_predictions("MLP Link Predictor", y_test, mlp_prob))
        models["MLP Link Predictor"] = mlp

        # Heuristic tensors
        H_train = _to_device(torch.tensor(heuristics.batch(train_df), dtype=torch.float32), cfg.device)
        H_val   = _to_device(torch.tensor(heuristics.batch(val_df),   dtype=torch.float32), cfg.device)
        H_test  = _to_device(torch.tensor(heuristics.batch(test_df),  dtype=torch.float32), cfg.device)

        tr_src, tr_dst, tr_y = _df_to_link_tensors(train_df, node_to_idx, cfg.device)
        vl_src, vl_dst, _    = _df_to_link_tensors(val_df,   node_to_idx, cfg.device)
        ts_src, ts_dst, _    = _df_to_link_tensors(test_df,  node_to_idx, cfg.device)

        gnn_splits = dict(
            train_src=tr_src, train_dst=tr_dst, train_y=tr_y,
            val_src=vl_src,   val_dst=vl_dst,   val_y_np=y_val,
            test_src=ts_src,  test_dst=ts_dst,
            H_train=H_train,  H_val=H_val,      H_test=H_test,
        )

        # ── GCN ───────────────────────────────────────────────────────────────
        gcn = GCNLinkPredictionModel(X_nodes.shape[1], cfg).to(cfg.device)
        gcn.init_buffers(pagerank, node_ids, num_bias)
        gcn_prob = _train_gnn(gcn, "GCN", gnn_splits, X_nodes, adj_norm, cfg)
        results.append(evaluate_predictions("GCN Link Prediction", y_test, gcn_prob))
        models["GCN Link Prediction"] = gcn

        # ── GraphSAGE ─────────────────────────────────────────────────────────
        sage = GraphSAGELinkPredictionModel(X_nodes.shape[1], cfg).to(cfg.device)
        sage.init_buffers(pagerank, node_ids, num_bias)
        sage_prob = _train_gnn(sage, "GraphSAGE", gnn_splits, X_nodes, adj_norm, cfg)
        results.append(evaluate_predictions("GraphSAGE Link Prediction", y_test, sage_prob))
        models["GraphSAGE Link Prediction"] = sage

    # ── Best model this seed ───────────────────────────────────────────────────
    best_name = max(results, key=lambda x: x["roc_auc"])["model"]
    best_auc  = next(r["roc_auc"] for r in results if r["model"] == best_name)
    if best_auc > global_state["best_auc"]:
        global_state.update(best_auc=best_auc, best_clf=models[best_name], best_name=best_name)
    log.info("  Best this seed: %s (AUC=%.4f)", best_name, best_auc)

    # ── Score all candidates ───────────────────────────────────────────────────
    all_src    = nodes["id"].tolist()
    tgt_pool   = list(N)
    cand_df    = pd.DataFrame(
        [(s, t) for s in all_src for t in tgt_pool if s != t],
        columns=["source", "target"],
    )

    if HAS_TORCH:
        H_cand = _to_device(
            torch.tensor(heuristics.batch(cand_df), dtype=torch.float32), cfg.device
        )
    else:
        H_cand = heuristics.batch(cand_df)  # numpy fallback

    cand_df["probability"] = _score_candidates(
        best_name, models[best_name], cand_df, H_cand,
        X_nodes, adj_norm, node_to_idx, pf, cfg,
    )
    cand_df["known_positive"]       = cand_df.apply(
        lambda r: (r["source"], r["target"]) in pos_set, axis=1
    )
    cand_df["numeric_score_target"] = cand_df["target"].map(
        lambda t: num_scores.get(t, 0.0)
    )
    return results, cand_df.sort_values("probability", ascending=False)


# =============================================================================
# 14.  MULTI-SEED PIPELINE (TASK 2)
# =============================================================================

def run_task2(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    numeric_raw_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> dict:
    """
    Execute Task 2: multi-seed link prediction over all model types.

    Returns a rich dict consumed by run_task3 and run_task4.
    """
    # ── Dataset & graphs ──────────────────────────────────────────────────────
    _, _, dataset, pos_set, N = build_dataset(nodes, edges, cfg)
    G_full = build_graph(nodes, edges)
    G_mp   = build_graph(nodes, edges, exclude_pairs=pos_set)
    log.info(
        "G_full: %d/%d | G_mp: %d/%d",
        G_full.number_of_nodes(), G_full.number_of_edges(),
        G_mp.number_of_nodes(),   G_mp.number_of_edges(),
    )

    pagerank = (
        nx.pagerank(G_mp) if G_mp.number_of_edges() > 0
        else {n: 0.0 for n in G_mp.nodes()}
    )
    numeric_scores = build_numeric_node_scores(numeric_raw_df, cfg)

    nf = build_node_features(G_mp, nodes, numeric_raw_df, pagerank, cfg)
    adj_norm   = build_adjacency(nf["node_ids"], nf["node_to_idx"], G_mp, cfg)
    heuristics = GraphHeuristics(G_mp, pagerank)

    # Determine pair feature dimension
    _sample = build_pair_features(
        dataset.head(5), nf["X_nodes_np"], nf["node_to_idx"], pagerank,
        nf["type_map"], heuristics, numeric_scores, nf["numeric_feat_matrix"], cfg,
    )
    context_dim = _sample.shape[1]
    log.info("Pair feature dim: %d", context_dim)

    global_state = {"best_auc": 0.0, "best_clf": None, "best_name": None}

    shared = dict(
        dataset=dataset, nodes=nodes, pos_set=pos_set, N=N,
        X_nodes=nf["X_nodes"], X_nodes_np=nf["X_nodes_np"],
        adj_norm=adj_norm, node_to_idx=nf["node_to_idx"],
        node_ids=nf["node_ids"], numeric_scores=numeric_scores,
        heuristics=heuristics, numeric_feat_matrix=nf["numeric_feat_matrix"],
        pagerank=pagerank, type_map=nf["type_map"],
        context_dim=context_dim, numeric_bias_tensor=nf["numeric_bias_tensor"],
        global_state=global_state,
    )

    all_results: List[dict] = []
    all_reco:    List[pd.DataFrame] = []

    for seed in cfg.seeds:
        r, cdf = run_one_seed(seed, shared, cfg)
        all_results.extend(r)
        all_reco.append(cdf)

    log.info("All seeds done.")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    full_df = pd.DataFrame(all_results)
    n_models = len([m for m in MODEL_COLORS if not (not HAS_TORCH and m in
                   ("MLP Link Predictor","GCN Link Prediction","GraphSAGE Link Prediction"))
                   and not (not HAS_XGB and m == "XGBoost")])
    full_df["seed"] = [s for s in cfg.seeds for _ in range(n_models)][:len(full_df)]

    summary_df = (
        full_df.groupby("model")[METRICS].agg(["mean", "std"]).round(4)
    )
    summary_df.columns = ["_".join(c) for c in summary_df.columns]
    summary_df = summary_df.sort_values("roc_auc_mean", ascending=False).reset_index()

    all_reco_df = pd.concat(all_reco, ignore_index=True)
    agg_reco_df = (
        all_reco_df.groupby(["source", "target"], as_index=False).agg(
            probability_mean     =("probability",          "mean"),
            probability_std      =("probability",          "std"),
            numeric_score_target =("numeric_score_target", "first"),
            known_positive       =("known_positive",       "first"),
        )
    )
    agg_reco_df["source_type"] = agg_reco_df["source"].map(nf["type_map"])
    agg_reco_df["target_type"] = agg_reco_df["target"].map(nf["type_map"])
    agg_reco_df["score_final"] = _apply_numeric_boost(agg_reco_df, numeric_scores, cfg)
    agg_reco_df = agg_reco_df.sort_values("score_final", ascending=False).reset_index(drop=True)

    topk = (
        agg_reco_df.groupby("source", group_keys=False)
        .head(cfg.top_k)
        .reset_index(drop=True)
    )
    log.info("Aggregated: top-%d recommendations → %d rows.", cfg.top_k, len(topk))

    # ── Persist ───────────────────────────────────────────────────────────────
    _persist_task2_artifacts(
        global_state, nf, numeric_scores, numeric_raw_df, context_dim, N, cfg
    )

    # ── Exports ───────────────────────────────────────────────────────────────
    agg_reco_df.to_csv(os.path.join(cfg.output_dir, "best_model_all_predictions.csv"), index=False)
    topk.to_csv(os.path.join(cfg.output_dir, "best_model_topk.csv"), index=False)
    _export_numeric_scores(numeric_scores, nf["type_map"], numeric_raw_df, cfg)

    return dict(
        summary_df=summary_df,
        topk_recommendations=topk,
        agg_reco_df=agg_reco_df,
        numeric_scores=numeric_scores,
        pos_set=pos_set,
        N=N,
        G_full=G_full,
        G_mp=G_mp,
        pagerank=pagerank,
        global_state=global_state,
        **{k: nf[k] for k in ("node_to_idx", "idx_to_node", "X_nodes_np",
                               "type_map", "node_types", "numeric_feat_matrix")},
        numeric_raw_df=numeric_raw_df,
        context_dim=context_dim,
    )


def _persist_task2_artifacts(
    global_state: dict,
    nf: dict,
    numeric_scores: Dict[str, float],
    numeric_raw_df: pd.DataFrame,
    context_dim: int,
    N: Set[str],
    cfg: PipelineConfig,
) -> None:
    """Save best classifier and feature artifacts for Task 4 cold-start."""
    import joblib

    feature_artifacts = {
        "classifier_type":            global_state["best_name"],
        "node_to_idx":                nf["node_to_idx"],
        "idx_to_node":                nf["idx_to_node"],
        "X_nodes_np":                 nf["X_nodes_np"],
        "pagerank":                   {},  # populated below
        "_type_map":                  dict(nf["type_map"]),
        "node_types":                 list(nf["node_types"]),
        "_numeric_feat_matrix":       nf["numeric_feat_matrix"],
        "numeric_node_scores":        dict(numeric_scores),
        "NUMERIC_PROPERTIES":         list(cfg.numeric.properties),
        "NUMERIC_PROPERTIES_WEIGHTS": dict(cfg.numeric.weights),
        "NUMERIC_FEATURE_WEIGHT":     cfg.numeric.feature_weight,
        "CONTEXT_DIM":                context_dim,
        "targets":                    list(N),
        "numeric_minmax": {
            col: (float(numeric_raw_df[col].dropna().min()), float(numeric_raw_df[col].dropna().max()))
            for col in cfg.numeric.properties if col in numeric_raw_df.columns
        },
    }

    clf_path  = os.path.join(cfg.output_dir, "best_classifier.pkl")
    arts_path = os.path.join(cfg.output_dir, "inference_artifacts.pkl")

    joblib.dump(global_state["best_clf"], clf_path)
    with open(arts_path, "wb") as f:
        pickle.dump(feature_artifacts, f)

    log.info(
        "Best classifier (%s, AUC=%.4f) → %s",
        global_state["best_name"], global_state["best_auc"], clf_path,
    )


def _export_numeric_scores(
    numeric_scores: Dict[str, float],
    type_map: Dict[str, str],
    numeric_raw_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> None:
    rows = []
    for node_id, agg_score in numeric_scores.items():
        row = {"node": node_id, "type": type_map.get(node_id, "unknown"),
               "agg_score": round(agg_score, 6)}
        for prop in cfg.numeric.properties:
            if prop in numeric_raw_df.columns:
                row[prop + "_raw"] = (
                    numeric_raw_df.at[node_id, prop]
                    if node_id in numeric_raw_df.index else np.nan
                )
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("agg_score", ascending=False)
    out.to_csv(os.path.join(cfg.output_dir, "numeric_node_scores.csv"), index=False)


# =============================================================================
# 15.  TASK 2 VISUALISATIONS
# =============================================================================

def plot_numeric_vs_probability(agg_reco_df: pd.DataFrame, cfg: PipelineConfig) -> None:
    """Scatter: target numeric score vs. model probability (unknown & known)."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, subset, title, color in [
        (axes[0], agg_reco_df[~agg_reco_df["known_positive"]], "Unknown candidates", "#5B8DEF"),
        (axes[1], agg_reco_df[ agg_reco_df["known_positive"]], "Known positive links", "#3EC97C"),
    ]:
        if subset.empty:
            ax.set_title(title + " (empty)")
            continue
        ax.scatter(subset["numeric_score_target"], subset["probability_mean"],
                   alpha=0.35, s=12, color=color)
        x_, y_ = subset["numeric_score_target"].values, subset["probability_mean"].values
        if x_.std() > 1e-6:
            z  = np.polyfit(x_, y_, 1)
            xs = np.linspace(x_.min(), x_.max(), 100)
            ax.plot(xs, np.poly1d(z)(xs), "r--", linewidth=1.5,
                    label=f"Trend (slope={z[0]:.3f})")
            ax.legend(fontsize=9)
        ax.set_xlabel("Normalised numeric score (target)")
        ax.set_ylabel("Link probability (model)")
        ax.set_title(title, fontweight="bold")
    fig.suptitle(
        f"Numeric properties impact\n({', '.join(cfg.numeric.properties)})",
        fontweight="bold", fontsize=12,
    )
    plt.tight_layout()
    plt.savefig(os.path.join(cfg.output_dir, "fig_numeric_vs_probability.png"), dpi=150)
    plt.close(fig)


def plot_numeric_property_summary(
    N: Set[str],
    numeric_raw_df: pd.DataFrame,
    cfg: PipelineConfig,
) -> None:
    """Bar chart: mean raw numeric values across target nodes."""
    present = [c for c in cfg.numeric.properties if c in numeric_raw_df.columns]
    if not present:
        return
    prop_means = {
        p: float(np.mean(numeric_raw_df.loc[numeric_raw_df.index.isin(N), p].dropna().values))
        for p in present
        if len(numeric_raw_df.loc[numeric_raw_df.index.isin(N), p].dropna()) > 0
    }
    items = sorted(prop_means.items(), key=lambda x: x[1], reverse=True)
    labels_ = [p for p, _ in items]
    values_ = [v for _, v in items]
    colors_ = ["#5B8DEF" if cfg.numeric.weights.get(p, 0) >= 0.3 else "#A0BEF5" for p in labels_]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(range(len(labels_)), values_, color=colors_, alpha=0.85, edgecolor="white")
    ax.set_xticks(range(len(labels_)))
    ax.set_xticklabels(
        [f"{p}\n(w={cfg.numeric.weights.get(p, 0):.2f})" for p in labels_],
        rotation=20, ha="right", fontsize=9,
    )
    ax.set_ylabel("Mean raw value")
    ax.set_title("Numeric properties — mean across target nodes", fontweight="bold")
    plt.tight_layout()
    plt.savefig(os.path.join(cfg.output_dir, "fig_numeric_properties_summary.png"), dpi=150)
    plt.close(fig)


# =============================================================================
# 16.  TASK 3 — NEURO-SYMBOLIC FILTERING & RANKING
# =============================================================================

def _bfs_k_shortest(
    G_undir: nx.Graph,
    source: str,
    target: str,
    cc_map: Dict[str, int],
    sym_cfg: SymbolicConfig,
) -> List[List[str]]:
    """Return up to k shortest paths (hop-limited); empty list if unreachable."""
    if source not in G_undir or target not in G_undir:
        return []
    if cc_map.get(source, -1) != cc_map.get(target, -2):
        return []
    try:
        paths = []
        for path in nx.shortest_simple_paths(G_undir, source, target):
            if len(path) - 1 > sym_cfg.bfs_cutoff:
                break
            paths.append(path)
            if len(paths) >= sym_cfg.bfs_max_paths:
                break
        return paths
    except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
        return []


def _score_influent_nodes(
    paths: List[List[str]],
    pagerank: Dict[str, float],
) -> List[dict]:
    """Score bridging nodes: 0.7×freq + 0.3×PageRank_norm."""
    if not paths:
        return []
    freq: Dict[str, int] = defaultdict(int)
    for path in paths:
        for n in path[1:-1]:
            freq[n] += 1
    pr_max = max(pagerank.values(), default=1.0) or 1.0
    results = [
        {"node": n, "count": c,
         "score": round(0.7 * (c / len(paths)) + 0.3 * pagerank.get(n, 0.0) / pr_max, 6)}
        for n, c in freq.items()
    ]
    return sorted(results, key=lambda x: x["score"], reverse=True)


def _edge_relations(path: List[str], G_sym: nx.DiGraph) -> List[str]:
    """Extract relation labels along a path."""
    rels = []
    for a, b in zip(path, path[1:]):
        if G_sym.has_edge(a, b):
            rels.append(G_sym[a][b].get("relation", "?"))
        elif G_sym.has_edge(b, a):
            rels.append(G_sym[b][a].get("relation", "?") + "(rev)")
        else:
            rels.append("?")
    return rels


def _build_bfs_analysis(
    pairs_df: pd.DataFrame,
    G_sym: nx.DiGraph,
    G_sym_undir: nx.Graph,
    cc_map: Dict[str, int],
    pagerank: Dict[str, float],
    sym_cfg: SymbolicConfig,
) -> Tuple[List[dict], Dict, Dict, float]:
    """BFS path analysis for all source-target pairs."""
    to_analyse = pairs_df[["source", "target"]].drop_duplicates()
    if sym_cfg.bfs_max_pairs is not None:
        to_analyse = to_analyse.head(sym_cfg.bfs_max_pairs)

    global_analysis: List[dict] = []
    for _, row in to_analyse.iterrows():
        src, tgt = str(row["source"]), str(row["target"])
        paths    = _bfs_k_shortest(G_sym_undir, src, tgt, cc_map, sym_cfg)
        global_analysis.append({
            "source":         src,
            "target":         tgt,
            "top_paths":      [{"path": p, "length": len(p)-1,
                                 "relations": _edge_relations(p, G_sym)} for p in paths],
            "influent_nodes": _score_influent_nodes(paths, pagerank),
            "n_paths_found":  len(paths),
        })

    ga_index = {(e["source"], e["target"]): e for e in global_analysis}
    bfs_values = [
        float(np.mean([n["score"] for n in e["influent_nodes"]])) if e["influent_nodes"] else 0.0
        for e in global_analysis
    ]
    bfs_max        = max(bfs_values, default=1.0) or 1.0
    bfs_part_index = {(e["source"], e["target"]): bfs_values[i] for i, e in enumerate(global_analysis)}

    log.info(
        "BFS: %d pairs, %d with path.",
        len(global_analysis), sum(1 for e in global_analysis if e["n_paths_found"] > 0),
    )
    return global_analysis, ga_index, bfs_part_index, bfs_max


def _symbolic_confidence(
    source: str,
    target: str,
    G_sym: nx.DiGraph,
    G_sym_undir: nx.Graph,
    cc_map: Dict[str, int],
    pr_norm: Dict[str, float],
    bfs_part_index: Dict,
    bfs_max: float,
    sym_cfg: SymbolicConfig,
) -> Tuple[float, float, int]:
    """Compute symbolic confidence for (source, target). Returns (conf, base, dist)."""
    if cc_map.get(source, -1) != cc_map.get(target, -2):
        return 0.0, 0.0, -1
    if G_sym.has_edge(source, target) or G_sym.has_edge(target, source):
        path_len = 1
    elif source not in G_sym_undir or target not in G_sym_undir:
        return 0.0, 0.0, -1
    else:
        try:
            path_len = nx.shortest_path_length(G_sym_undir, source=source, target=target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return 0.0, 0.0, -1

    base     = 1.0 / path_len
    pr_bonus = pr_norm.get(target, 0.0)
    bfs_bon  = bfs_part_index.get((source, target), 0.0) / bfs_max
    conf     = sym_cfg.w_base * base + sym_cfg.w_pr * pr_bonus + sym_cfg.w_bfs * bfs_bon
    return min(conf, 1.0), base, path_len


def run_task3(task2_results: dict, cfg: PipelineConfig) -> dict:
    """
    Execute Task 3: symbolic filtering + neuro-symbolic fusion.
    """
    sym_cfg     = cfg.symbolic
    agg_reco_df = task2_results["agg_reco_df"]
    topk_reco   = task2_results["topk_recommendations"]
    G_full      = task2_results["G_full"]
    pagerank    = task2_results["pagerank"]

    G_sym       = G_full
    G_sym_undir = G_sym.to_undirected()
    cc_map: Dict[str, int] = {}
    for idx, comp in enumerate(nx.connected_components(G_sym_undir)):
        for n in comp:
            cc_map[n] = idx

    pr_max  = max(pagerank.values(), default=1.0) or 1.0
    pr_norm = {n: v / pr_max for n, v in pagerank.items()}

    t3_df = agg_reco_df.copy()
    t3_df["source"] = t3_df["source"].astype(str).str.strip()
    t3_df["target"] = t3_df["target"].astype(str).str.strip()

    # Regime detection
    dist_per_src = t3_df.groupby("source")["probability_mean"].nunique()
    flat_ratio   = (dist_per_src == 1).sum() / max(len(dist_per_src), 1)
    if flat_ratio > sym_cfg.flat_ratio_threshold:
        NEURAL_W, SYMBOLIC_W, regime = sym_cfg.neural_weight_flat, sym_cfg.symbolic_weight_flat, "FLAT"
    else:
        NEURAL_W, SYMBOLIC_W, regime = sym_cfg.neural_weight_normal, sym_cfg.symbolic_weight_normal, "NORMAL"
    log.info("Regime: %s (flat=%.1f%%)", regime, 100 * flat_ratio)

    global_analysis, ga_index, bfs_idx, bfs_max = _build_bfs_analysis(
        topk_reco, G_sym, G_sym_undir, cc_map, pagerank, sym_cfg
    )

    # Symbolic confidence
    conf_res = [
        _symbolic_confidence(r["source"], r["target"], G_sym, G_sym_undir,
                             cc_map, pr_norm, bfs_idx, bfs_max, sym_cfg)
        for _, r in t3_df.iterrows()
    ]
    t3_df["symbolic_confidence"] = [r[0] for r in conf_res]
    t3_df["sym_base_score"]      = [r[1] for r in conf_res]
    t3_df["path_length"]         = [r[2] for r in conf_res]

    def _cat(base: float) -> str:
        if base <= 0: return "rejected"
        if base >= 1: return "direct"
        return "indirect"
    t3_df["sym_category"] = t3_df["sym_base_score"].apply(_cat)

    n_tot = len(t3_df)
    n_dir = (t3_df["sym_category"] == "direct").sum()
    n_ind = (t3_df["sym_category"] == "indirect").sum()
    n_rej = (t3_df["sym_category"] == "rejected").sum()
    log.info("Layer 3: %d total | %d direct | %d indirect | %d rejected", n_tot, n_dir, n_ind, n_rej)

    # Neuro-symbolic score
    t3_df["neurosymbolic_score"] = np.where(
        t3_df["symbolic_confidence"] == 0.0,
        0.0,
        NEURAL_W * t3_df["probability_mean"] + SYMBOLIC_W * t3_df["symbolic_confidence"],
    )

    df_approved = t3_df[t3_df["neurosymbolic_score"] > 0].copy()
    df_rejected = t3_df[t3_df["neurosymbolic_score"] == 0].copy()

    df_ranked = df_approved.sort_values("neurosymbolic_score", ascending=False).reset_index(drop=True)
    df_ranked.index += 1

    df_topk = (
        df_ranked.groupby("source", group_keys=False)
        .apply(lambda g: g.nlargest(cfg.top_k, "neurosymbolic_score"))
        .reset_index(drop=True)
    )
    df_topk = df_topk.copy()
    df_topk["top5_influent_nodes"] = df_topk.apply(
        lambda r: " | ".join(
            n["node"] for n in ga_index.get((r["source"], r["target"]), {}).get("influent_nodes", [])[:5]
        ), axis=1,
    )
    df_topk["best_ontology_path"] = df_topk.apply(
        lambda r: (
            " → ".join(ga_index[(r["source"], r["target"])]["top_paths"][0]["path"])
            if (r["source"], r["target"]) in ga_index and ga_index[(r["source"], r["target"])]["top_paths"]
            else "N/A"
        ), axis=1,
    )

    coverage = (
        t3_df.groupby("source").agg(
            total       =("target",              "count"),
            approved    =("neurosymbolic_score", lambda x: (x > 0).sum()),
            rejected    =("neurosymbolic_score", lambda x: (x == 0).sum()),
            mean_score  =("neurosymbolic_score", lambda x: x[x>0].mean() if (x>0).any() else 0.0),
            max_score   =("neurosymbolic_score", lambda x: x[x>0].max()  if (x>0).any() else 0.0),
            n_direct    =("sym_category", lambda x: (x == "direct").sum()),
        ).reset_index()
    )
    coverage["approval_rate"] = (coverage["approved"] / coverage["total"]).round(3)
    coverage = coverage.sort_values("mean_score", ascending=False).reset_index(drop=True)

    # Persist symbolic config for Task 4
    sym_cfg_obj = {
        "w_base": sym_cfg.w_base, "w_pr": sym_cfg.w_pr, "w_bfs": sym_cfg.w_bfs,
        "NEURAL_WEIGHT": NEURAL_W, "SYMBOLIC_WEIGHT": SYMBOLIC_W,
        "flat_ratio": float(flat_ratio), "regime": regime,
        "pr_norm": dict(pr_norm),
    }
    sym_cfg_path = os.path.join(cfg.t3_dir, "sym_config.pkl")
    with open(sym_cfg_path, "wb") as f:
        pickle.dump(sym_cfg_obj, f)

    # Exports
    df_ranked.to_csv(os.path.join(cfg.t3_dir, "task3_all_approved_ranked.csv"), index=False)
    df_topk.to_csv(  os.path.join(cfg.t3_dir, "task3_topk_per_topic.csv"),      index=False)
    df_rejected.to_csv(os.path.join(cfg.t3_dir, "task3_rejected_predictions.csv"), index=False)
    coverage.to_csv(   os.path.join(cfg.t3_dir, "task3_topic_coverage.csv"),        index=False)
    t3_df.to_csv(      os.path.join(cfg.t3_dir, "task3_full_scored.csv"),           index=False)

    ga_export = [
        {"source": e["source"], "target": e["target"],
         "n_paths_found": e["n_paths_found"],
         "top_paths": [{"path": p["path"], "length": p["length"], "relations": p["relations"]}
                       for p in e["top_paths"]],
         "influent_nodes": e["influent_nodes"]}
        for e in global_analysis
    ]
    with open(os.path.join(cfg.t3_dir, "task3_global_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(ga_export, f, ensure_ascii=False, indent=2)

    log.info(
        "Task 3: %d approved, %d rejected, %d topics, top-%d: %d rows.",
        len(df_approved), len(df_rejected), df_topk["source"].nunique(), cfg.top_k, len(df_topk),
    )
    return dict(
        t3_df=t3_df, df_ranked=df_ranked, df_topk=df_topk, df_rejected=df_rejected,
        coverage=coverage, global_analysis=global_analysis, ga_index=ga_index,
        G_sym=G_sym, pr_norm=pr_norm,
        NEURAL_WEIGHT=NEURAL_W, SYMBOLIC_WEIGHT=SYMBOLIC_W,
        regime_label=regime,
        n_total=n_tot, n_direct=n_dir, n_indirect=n_ind, n_rejected=n_rej,
    )


# =============================================================================
# 17.  TASK 4 — ONTOLOGY PATH ENGINE
# =============================================================================

class OntologyPathEngine:
    """
    Cached shortest-path computation over a directed knowledge graph.
    Fully pickle-serialisable.
    """

    def __init__(self, G: nx.DiGraph):
        self.G       = G
        self.G_undir = G.to_undirected()
        self._cache: Dict[Tuple, List] = {}
        self._cc_map: Dict[str, int] = {}
        for i, comp in enumerate(nx.connected_components(self.G_undir)):
            for n in comp:
                self._cc_map[n] = i
        log.info(
            "OntologyPathEngine: %d nodes, %d edges, %d components.",
            G.number_of_nodes(), G.number_of_edges(), len(set(self._cc_map.values())),
        )

    def get_path(self, source: str, target: str) -> List[str]:
        key = (source, target)
        if key in self._cache:
            return self._cache[key]
        if self._cc_map.get(source, -1) != self._cc_map.get(target, -2):
            result: List[str] = []
        elif self.G.has_edge(source, target) or self.G.has_edge(target, source):
            result = [source, target]
        elif source not in self.G_undir or target not in self.G_undir:
            result = []
        else:
            try:
                result = nx.shortest_path(self.G_undir, source=source, target=target)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                result = []
        self._cache[key] = result
        return result

    def get_edge_relations(self, path: List[str]) -> List[str]:
        rels = []
        for a, b in zip(path, path[1:]):
            if self.G.has_edge(a, b):
                rels.append(self.G[a][b].get("relation", "?"))
            elif self.G.has_edge(b, a):
                rels.append(self.G[b][a].get("relation", "?") + "(rev)")
            else:
                rels.append("?")
        return rels

    def format_path(self, path: List[str]) -> str:
        if not path:
            return "no path found"
        rels = self.get_edge_relations(path)
        out  = path[0]
        for node, rel in zip(path[1:], rels):
            out += f" --{rel}--> {node}"
        return out

    def path_stats(self, source: str, target: str) -> dict:
        path = self.get_path(source, target)
        rels = self.get_edge_relations(path)
        return {
            "path":           path,
            "distance":       len(path) - 1 if path else -1,
            "relations":      rels,
            "key_relation":   rels[0] if rels else "unknown",
            "formatted_path": self.format_path(path),
        }

    def neighbours(self, node: str, depth: int = 1) -> List[str]:
        if node not in self.G_undir:
            return []
        visited, frontier = {node}, {node}
        for _ in range(depth):
            nxt = set()
            for n in frontier:
                nxt.update(self.G_undir.neighbors(n))
            nxt -= visited
            visited |= nxt
            frontier = nxt
        visited.discard(node)
        return list(visited)


# =============================================================================
# 18.  TASK 4 — EXPLANATION ENGINE
# =============================================================================

class ExplanationEngine:
    """
    Structured natural-language explanation generator.

    Blocks: strength, ontology, path, target, [context], [numeric_boost], [extra]
    """

    def __init__(
        self,
        path_engine: OntologyPathEngine,
        cfg: PipelineConfig,
        target_descriptions: Optional[Dict[str, str]] = None,
        extra_block_fn: Optional[Callable] = None,
    ):
        self.path_engine         = path_engine
        self.cfg                 = cfg
        self.target_descriptions = target_descriptions or {}
        self.extra_block_fn      = extra_block_fn

    # ── Blocks ────────────────────────────────────────────────────────────────

    def _block_strength(self, source: str, target: str, score: float, known: bool) -> str:
        status = "validated" if known else "novel"
        if score >= self.cfg.score_high:
            quality, confidence = "strongly recommended", "High confidence"
        elif score >= self.cfg.score_moderate:
            quality, confidence = "recommended", "Moderate confidence"
        else:
            quality, confidence = "proposed as an exploratory suggestion", "Weak confidence"
        return (
            f"The {self.cfg.target_label} '{target}' is {quality} for the "
            f"{self.cfg.source_label} '{source}' "
            f"(neuro-symbolic score: {score:.3f} — {confidence}, {status})."
        )

    def _block_ontology(self, sym_conf: float, ps: dict) -> str:
        dist, rels = ps["distance"], ps["relations"]
        if sym_conf == 0.0 or dist < 0:
            return "No ontological path was found to support this recommendation."
        if dist == 1:
            rel = rels[0] if rels else "direct"
            return (
                f"The ontology directly validates this recommendation "
                f"via a '{rel}' relation (confidence: {sym_conf:.2f})."
            )
        qualifier = (
            "strongly"  if sym_conf >= self.cfg.conf_high
            else "moderately" if sym_conf >= self.cfg.conf_moderate
            else "weakly"
        )
        return (
            f"The ontology {qualifier} supports this recommendation through "
            f"{dist - 1} intermediate concept(s) "
            f"(confidence: {sym_conf:.2f}, path length: {dist})."
        )

    def _block_path(self, ps: dict) -> str:
        fp = ps["formatted_path"]
        return f"Ontological path: [{fp}]." if fp != "no path found" and ps["distance"] >= 1 else ""

    def _block_target(self, target: str) -> str:
        if target in self.target_descriptions:
            desc = self.target_descriptions[target]
        else:
            desc = f"an element related to '{re.sub(r'[_-]', ' ', target).strip()}'"
        return f"'{target}' is {desc}."

    # ── Generation ────────────────────────────────────────────────────────────

    def generate(self, row: pd.Series, ps: dict) -> dict:
        source = str(row["source"])
        target = str(row["target"])
        score  = safe_float(row.get("neurosymbolic_score", 0.0))
        sym_c  = safe_float(row.get("symbolic_confidence", 0.0))
        known  = bool(row.get("known_positive", False))

        blocks: Dict[str, str] = {
            "strength": self._block_strength(source, target, score, known),
            "ontology": self._block_ontology(sym_c, ps),
            "path":     self._block_path(ps),
            "target":   self._block_target(target),
        }

        for opt_key in ("context_impact", "numeric_boost"):
            v = row.get(opt_key)
            if v and pd.notna(v):
                blocks[opt_key] = str(v)

        if ps.get("used_proxy_pivot"):
            blocks["pivot_reasoning"] = (
                f"The property '{ps['used_proxy_pivot']}' was used as a logical "
                f"pivot to connect this node to the ontology graph."
            )

        if self.extra_block_fn is not None:
            extra = self.extra_block_fn(row, ps)
            if extra:
                blocks["extra"] = extra

        return {
            "explanation":        " ".join(b for b in blocks.values() if b),
            "explanation_blocks": json.dumps(blocks, ensure_ascii=False),
        }

    def generate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enrich df with explanation columns; return reordered DataFrame."""
        records = []
        for _, row in df.iterrows():
            ps  = self.path_engine.path_stats(str(row["source"]), str(row["target"]))
            exp = self.generate(row, ps)
            sym_c = safe_float(row.get("symbolic_confidence", 0.0))
            records.append({
                **row.to_dict(),
                "confidence_label": conf_label(sym_c, self.cfg),
                "path_distance":    ps["distance"],
                "key_relation":     ps["key_relation"],
                "ontology_path":    ps["formatted_path"],
                **exp,
            })
        out     = pd.DataFrame(records)
        ordered = [c for c in OUTPUT_COLS if c in out.columns]
        extra   = [c for c in out.columns if c not in ordered]
        return out[ordered + extra].reset_index(drop=True)

    def generate_contrastive(
        self,
        source: str,
        chosen: str,
        alternative: str,
        chosen_score: float,
        alt_score: float,
        chosen_conf: float,
        alt_conf: float,
    ) -> str:
        """Explain why *chosen* was preferred over *alternative* for *source*."""
        cps = self.path_engine.path_stats(source, chosen)
        aps = self.path_engine.path_stats(source, alternative)
        reasons: List[str] = []

        diff = chosen_score - alt_score
        if abs(diff) >= 0.01:
            reasons.append(
                f"'{chosen}' has a {'higher' if diff > 0 else 'lower'} overall score "
                f"({chosen_score:.3f} vs {alt_score:.3f})."
            )

        cd, ad = cps["distance"], aps["distance"]
        if cd > 0 and ad > 0 and cd != ad:
            closer = chosen if cd < ad else alternative
            reasons.append(
                f"'{closer}' is ontologically closer "
                f"(distance {min(cd,ad)} vs {max(cd,ad)})."
            )
        elif cd > 0 > ad:
            reasons.append(
                f"'{chosen}' is reachable ({cd} step(s)); '{alternative}' is not connected."
            )

        if abs(chosen_conf - alt_conf) >= 0.05:
            reasons.append(
                f"Ontological confidence is {'stronger' if chosen_conf > alt_conf else 'weaker'} "
                f"for '{chosen}' ({chosen_conf:.2f} vs {alt_conf:.2f})."
            )

        if cd == 1 and ad != 1:
            rel = cps["relations"][0] if cps["relations"] else "direct"
            reasons.append(
                f"'{chosen}' is directly linked via '{rel}'; '{alternative}' needs intermediate concepts."
            )

        if not reasons:
            reasons.append(
                f"Both are similar; '{chosen}' is ranked first by marginal difference."
            )

        return f"Why '{chosen}' over '{alternative}' for '{source}': " + " ".join(reasons)


# =============================================================================
# 19.  TASK 4 — INFERENCE BUNDLES
# =============================================================================

class Task4Bundle:
    """
    Deployment bundle for known-source recommendation inference.
    Pickle-serialisable for offline persistence.
    """

    VERSION = "1.1.0"

    def __init__(
        self,
        path_engine: OntologyPathEngine,
        explanation_engine: ExplanationEngine,
        topk_df: pd.DataFrame,
        meta: Optional[dict] = None,
    ):
        self.path_engine        = path_engine
        self.explanation_engine = explanation_engine
        self.topk_df            = topk_df.copy()
        self.meta               = meta or {}
        self.meta["built_at"]          = datetime.utcnow().isoformat() + "Z"
        self.meta["version"]           = self.VERSION
        self.meta["n_recommendations"] = len(topk_df)

    # ── Public API ────────────────────────────────────────────────────────────

    def predict(
        self,
        source: str,
        target: Optional[str] = None,
        top_k: int = 5,
    ) -> List[dict]:
        df   = self.topk_df.copy()
        mask = df["source"].astype(str).str.strip() == source.strip()
        if not mask.any():
            return [{"error": f"Source '{source}' not found. Use predict_new() for unknown nodes."}]
        subset = df[mask]
        if target is not None:
            subset = subset[subset["target"].astype(str).str.strip() == target.strip()]
        subset = subset.sort_values("neurosymbolic_score", ascending=False).head(top_k)
        return self._rows_to_results(subset)

    def explain_contrastive(self, source: str, target_a: str, target_b: str) -> str:
        def _get(tgt):
            r = self.topk_df[(self.topk_df["source"] == source) & (self.topk_df["target"] == tgt)]
            if r.empty:
                return 0.0, 0.0
            return safe_float(r.iloc[0].get("neurosymbolic_score")), safe_float(r.iloc[0].get("symbolic_confidence"))
        sa, ca = _get(target_a)
        sb, cb = _get(target_b)
        return self.explanation_engine.generate_contrastive(source, target_a, target_b, sa, sb, ca, cb)

    def list_sources(self) -> List[str]:
        return sorted(self.topk_df["source"].astype(str).unique().tolist())

    def list_targets(self) -> List[str]:
        return sorted(self.topk_df["target"].astype(str).unique().tolist())

    def schema(self) -> dict:
        return {
            "version":   self.VERSION,
            "built_at":  self.meta.get("built_at"),
            "meta":      self.meta,
            "sources":   self.list_sources(),
            "targets":   self.list_targets(),
            "endpoints": {
                "POST /predict":     {"body": {"source": "str", "target": "str?", "top_k": "int=5"}},
                "POST /predict_new": {"body": {"node_name": "str", "node_context": "dict?", "top_k": "int=5"}},
                "POST /contrastive": {"body": {"source": "str", "target_a": "str", "target_b": "str"}},
                "GET /sources": {}, "GET /targets": {}, "GET /health": {},
            },
        }

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)
        log.info("Bundle v%s → %s (%.1f KB)", self.VERSION, path, os.path.getsize(path) / 1024)

    @classmethod
    def load(cls, path: str) -> "Task4Bundle":
        class _Unpickler(pickle.Unpickler):
            def find_class(self, module, name):
                if module in ("__main__", "pipeline"):
                    module = "nsxai.ml.pipeline"
                return super().find_class(module, name)
        with open(path, "rb") as f:
            obj = _Unpickler(f).load()
        log.info("Bundle loaded: %s | v%s | %d recs.", path, obj.meta.get("version"), obj.meta.get("n_recommendations"))
        return obj

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rows_to_results(self, subset: pd.DataFrame) -> List[dict]:
        """Convert a subset of topk_df rows to result dicts with explanations."""
        num_scores = getattr(self, "feature_artifacts", {}).get("numeric_node_scores", {})
        results    = []
        for _, row in subset.iterrows():
            row = row.copy()
            tgt = str(row["target"])
            tgt_num = float(num_scores.get(tgt, 0.0))
            if tgt_num > 0.3:
                row["numeric_boost"] = (
                    f"The recommendation '{tgt}' is reinforced by strong numeric properties "
                    f"(score={tgt_num:.2f})."
                )
            ps   = self.path_engine.path_stats(str(row["source"]), tgt)
            exp  = self.explanation_engine.generate(row, ps)
            sym_c = safe_float(row.get("symbolic_confidence", 0.0))
            results.append({
                "source":              str(row["source"]),
                "target":              tgt,
                "neurosymbolic_score": safe_float(row.get("neurosymbolic_score")),
                "probability_mean":    safe_float(row.get("probability_mean")),
                "symbolic_confidence": sym_c,
                "confidence_label":    conf_label(sym_c, self.explanation_engine.cfg),
                "known_positive":      bool(row.get("known_positive", False)),
                "path_distance":       ps["distance"],
                "key_relation":        ps.get("key_relation", "unknown"),
                "ontology_path":       ps["formatted_path"],
                "explanation":         exp["explanation"],
                "explanation_blocks":  json.loads(exp["explanation_blocks"]),
            })
        return results


# =============================================================================
# 20.  NSXAI INFERENCE BUNDLE (extends Task4Bundle with cold-start)
# =============================================================================

class NSXAIInferenceBundle(Task4Bundle):
    """
    Extended bundle supporting cold-start (unknown source) inference.

    Uses the stored classifier from Task 2 + feature artifacts to score
    any new node against all known targets.
    """

    VERSION = "2.0.0"

    _SYM_DEFAULTS = {
        "w_base": 0.70, "w_pr": 0.20, "w_bfs": 0.10,
        "NEURAL_WEIGHT": 0.35, "SYMBOLIC_WEIGHT": 0.65, "pr_norm": {},
    }

    def __init__(
        self,
        *,
        path_engine: OntologyPathEngine,
        explanation_engine: ExplanationEngine,
        topk_df: pd.DataFrame,
        meta: Optional[dict] = None,
        classifier=None,
        feature_artifacts: Optional[dict] = None,
        sym_config: Optional[dict] = None,
    ):
        super().__init__(path_engine, explanation_engine, topk_df, meta)
        self.classifier        = classifier
        self.feature_artifacts = feature_artifacts or {}
        self.sym_config        = {**self._SYM_DEFAULTS, **(sym_config or {})}
        self.meta["version"]   = self.VERSION

    def can_infer_new(self) -> bool:
        return (
            self.classifier is not None
            and bool(self.feature_artifacts)
            and "node_to_idx" in self.feature_artifacts
            and "X_nodes_np" in self.feature_artifacts
        )

    # ── Feature reconstruction ────────────────────────────────────────────────

    def _build_source_feature(self, node_context: dict) -> np.ndarray:
        """Reconstruct a node feature vector for an unseen source."""
        arts = self.feature_artifacts
        ctx  = node_context or {}

        graph_raw = np.array([
            float(ctx.get("in_degree", 0)),
            float(ctx.get("out_degree", 0)),
            float(ctx.get("degree_centrality", 0)),
            float(ctx.get("pagerank", 0)),
        ], dtype=np.float32)

        scaler = arts.get("scaler")
        if scaler is not None:
            try:
                graph_feat = scaler.transform(graph_raw.reshape(1, -1))[0].astype(np.float32)
            except Exception:
                graph_feat = graph_raw
        else:
            means = np.array(arts.get("graph_means", [0.0] * 4), dtype=np.float32)
            stds  = np.array(arts.get("graph_stds",  [1.0] * 4), dtype=np.float32)
            graph_feat = (graph_raw - means) / (stds + 1e-9)

        node_types = arts.get("node_types", [])
        ntype      = str(ctx.get("type", "unknown"))
        type_feat  = np.array([1.0 if ntype == t else 0.0 for t in node_types], dtype=np.float32)

        NP  = arts.get("NUMERIC_PROPERTIES", [])
        NW  = arts.get("NUMERIC_PROPERTIES_WEIGHTS", {})
        mm  = arts.get("numeric_minmax", {})
        nf  = []
        for prop in NP:
            raw = float(ctx.get(prop, 0.0))
            lo, hi = mm.get(prop, (0.0, 1.0))
            nf.append(np.clip((raw - lo) / (hi - lo + 1e-9), 0.0, 1.0) * NW.get(prop, 1.0))
        num_feat = np.array(nf, dtype=np.float32)

        raw = np.concatenate([graph_feat, type_feat, num_feat])
        target_dim = arts.get("X_nodes_np", np.zeros((1, 1))).shape[1]
        if len(raw) < target_dim:
            raw = np.pad(raw, (0, target_dim - len(raw)))
        else:
            raw = raw[:target_dim]
        return raw.astype(np.float32)

    def _build_pair_vector(self, src_feat: np.ndarray, tgt_name: str) -> np.ndarray:
        """Build pair feature vector for (src_feat, tgt_name)."""
        arts = self.feature_artifacts
        ni   = arts.get("node_to_idx", {})
        xn   = arts.get("X_nodes_np", np.zeros((1, 1)))
        NP   = arts.get("NUMERIC_PROPERTIES", [])
        NF_W = arts.get("NUMERIC_FEATURE_WEIGHT", 1.0)
        pr   = arts.get("pagerank", {})
        nns  = arts.get("numeric_node_scores", {})
        nmx  = arts.get("_numeric_feat_matrix", np.zeros((0, 0)))

        if tgt_name not in ni:
            cd = arts.get("CONTEXT_DIM", len(src_feat) * 4 + 10 + 3 + 1)
            return np.zeros(cd, dtype=np.float32)

        ti       = ni[tgt_name]
        dst_feat = xn[ti].astype(np.float32)
        K        = len(NP)
        score_d  = float(nns.get(tgt_name, 0.0))
        ppd      = nmx[ti].astype(np.float32) if ti < len(nmx) and K > 0 else np.zeros(K, dtype=np.float32)
        pps      = np.zeros(K, dtype=np.float32)

        num_base = np.array([
            score_d, 0.0, abs(score_d), 0.0,
            float(np.max(ppd)) if K > 0 else 0.0,
        ], dtype=np.float32)
        num_feat = np.concatenate([num_base, ppd, pps]) * NF_W
        pr_dst   = float(pr.get(tgt_name, 0.0))

        pv = np.concatenate([
            src_feat, dst_feat,
            np.abs(src_feat - dst_feat), src_feat * dst_feat,
            np.zeros(10, dtype=np.float32),  # heuristics = 0 for cold-start
            np.array([0.0, pr_dst, pr_dst], dtype=np.float32),
            np.array([0.0], dtype=np.float32),
            num_feat,
        ]).astype(np.float32)

        cd = arts.get("CONTEXT_DIM")
        if cd:
            pv = np.pad(pv, (0, max(0, cd - len(pv))))[:cd]
        return pv

    def _neural_predict(self, pv: np.ndarray, src_feat: np.ndarray = None, tgt: str = None) -> float:
        """Run stored classifier on a pair vector → P(link)."""
        try:
            clf = self.classifier
            if hasattr(clf, "predict_proba"):
                return float(clf.predict_proba(pv.reshape(1, -1))[0, 1])
            if HAS_TORCH:
                clf.eval()
                with torch.no_grad():
                    if type(clf).__name__ in ("GCNLinkPredictionModel", "GraphSAGELinkPredictionModel"):
                        if src_feat is None or tgt is None:
                            return 0.0
                        arts = self.feature_artifacts
                        tgt_idx = arts.get("node_to_idx", {}).get(tgt)
                        if tgt_idx is None:
                            return 0.0
                        
                        x_pair = torch.tensor(np.vstack([src_feat, arts["X_nodes_np"][tgt_idx]]), dtype=torch.float32).to(clf.node_pr.device)
                        adj_iso = torch.eye(2).to(clf.node_pr.device)
                        pr_pair = torch.tensor([[0.0], [float(arts.get("pagerank", {}).get(tgt, 0.0))]], dtype=torch.float32).to(clf.node_pr.device)
                        nb_pair = torch.tensor([[0.0], [clf.node_num_bias[tgt_idx].item()]], dtype=torch.float32).to(clf.node_pr.device)
                        
                        scale_pair = 1.0 + nb_pair * clf._boost
                        h_pair = clf.enc1(x_pair * scale_pair, adj_iso, pr_pair)
                        z_pair = clf.enc2(h_pair * scale_pair, adj_iso, pr_pair)
                        
                        heur = torch.zeros((1, 10), dtype=torch.float32).to(clf.node_pr.device)
                        out = clf.decoder(z_pair[0:1], z_pair[1:2], heur, pr_pair[0:1], pr_pair[1:2], nb_pair[1:2])
                        return float(torch.sigmoid(out).item())
                    else:
                        t = torch.tensor(pv, dtype=torch.float32).unsqueeze(0).to(next(clf.parameters()).device if hasattr(clf, "parameters") else "cpu")
                        return float(torch.sigmoid(clf(t)).item())
        except Exception as e:
            log.debug("_neural_predict error: %s", e)
        return 0.0

    def _sym_confidence_cold(self, ps: dict, target: str) -> float:
        """Symbolic confidence without BFS bonus (unavailable for new nodes)."""
        sc = self.sym_config
        d  = ps["distance"]
        if d < 0:
            return 0.0
        base     = 1.0 / d if d > 0 else 1.0
        pr_bonus = sc.get("pr_norm", {}).get(target, 0.0)
        return float(min(sc["w_base"] * base + sc["w_pr"] * pr_bonus, 1.0))

    def _resolve_path_with_proxy(self, node_name: str, tgt: str, ctx: dict) -> dict:
        """
        If no direct path, try proxy pivots from context (type, string values).
        Returns a path_stats dict with distance >= 0, or the original (-1) dict.
        """
        ps = self.path_engine.path_stats(node_name, tgt)
        if ps["distance"] >= 0:
            return ps

        proxies = []
        if "type" in ctx and isinstance(ctx["type"], str):
            proxies.append(ctx["type"])
        for k, v in ctx.items():
            if isinstance(v, str) and v and k != "type" and v not in proxies:
                if not v.replace(".", "", 1).isdigit():
                    proxies.append(v)

        best_ps, best_proxy = None, ""
        for proxy in proxies:
            p_ps = self.path_engine.path_stats(proxy, tgt)
            if p_ps["distance"] >= 0:
                if best_ps is None or p_ps["distance"] < best_ps["distance"]:
                    best_ps, best_proxy = p_ps, proxy

        if best_ps is not None:
            return {
                **best_ps,
                "distance":       best_ps["distance"] + 1,
                "formatted_path": f"{node_name} --context_link--> " + best_ps["formatted_path"],
                "path":           [node_name] + best_ps["path"],
                "used_proxy_pivot": best_proxy,
            }
        return ps

    def _build_numeric_boost_note(self, tgt: str) -> str:
        """Build numeric boost annotation for the target node."""
        arts          = self.feature_artifacts
        tgt_num_score = float(arts.get("numeric_node_scores", {}).get(tgt, 0.0))
        if tgt_num_score <= 0.3:
            return ""
        base = (
            f"The target '{tgt}' benefits from an attractiveness boost "
            f"(score={tgt_num_score:.2f})."
        )
        node_idx = arts.get("node_to_idx", {}).get(tgt)
        feat_mat = arts.get("_numeric_feat_matrix")
        num_props = arts.get("NUMERIC_PROPERTIES", [])
        if node_idx is not None and feat_mat is not None and node_idx < len(feat_mat):
            details = [
                f"'{p}' (impact={feat_mat[node_idx][i]:.2f})"
                for i, p in enumerate(num_props)
                if i < len(feat_mat[node_idx]) and feat_mat[node_idx][i] > 0.01
            ]
            if details:
                return base + " Key contributors: " + ", ".join(details) + "."
        return base

    def predict_new(
        self,
        node_name: str,
        node_context: Optional[dict] = None,
        top_k: int = 5,
    ) -> List[dict]:
        """Predict recommendations for an unseen (cold-start) source node."""
        if not self.can_infer_new():
            return [{"error": "Classifier not available. Ensure Task 2 produced best_classifier.pkl."}]

        ctx     = node_context or {}
        sc      = self.sym_config
        targets = self.feature_artifacts.get("targets", self.list_targets())
        src_feat = self._build_source_feature(ctx)
        results  = []

        for tgt in targets:
            ps      = self._resolve_path_with_proxy(node_name, tgt, ctx)
            pv      = self._build_pair_vector(src_feat, tgt)
            neural  = self._neural_predict(pv, src_feat=src_feat, tgt=tgt)
            sym     = self._sym_confidence_cold(ps, tgt)
            ns_score = sc["NEURAL_WEIGHT"] * neural + sc["SYMBOLIC_WEIGHT"] * sym if sym > 0 else 0.0
            if ns_score <= 0:
                continue

            row = pd.Series({
                "source":              node_name,
                "target":              tgt,
                "neurosymbolic_score": ns_score,
                "probability_mean":    neural,
                "symbolic_confidence": sym,
                "known_positive":      False,
                "context_impact":      self._build_context_impact_note(ctx, tgt),
                "numeric_boost":       self._build_numeric_boost_note(tgt),
            })
            exp = self.explanation_engine.generate(row, ps)

            results.append({
                "source":              node_name,
                "target":              tgt,
                "neurosymbolic_score": round(float(ns_score), 6),
                "neural_probability":  round(float(neural),   6),
                "probability_mean":    round(float(neural),   6),
                "symbolic_confidence": round(float(sym),      6),
                "confidence_label":    conf_label(sym, self.explanation_engine.cfg),
                "known_positive":      False,
                "path_distance":       ps["distance"],
                "key_relation":        ps.get("key_relation", "unknown"),
                "ontology_path":       ps["formatted_path"],
                "raw_path":            ps.get("path", []),
                "raw_relations":       ps.get("relations", []),
                "explanation":         exp["explanation"],
                "explanation_blocks":  json.loads(exp["explanation_blocks"]),
                "inference_mode":      "cold_start",
            })

        results.sort(key=lambda x: x["neurosymbolic_score"], reverse=True)
        return results[:top_k]

    def _build_context_impact_note(self, ctx: dict, tgt: str) -> str:
        """Build a human-readable note describing context feature impact."""
        if not ctx:
            return ""
        arts      = self.feature_artifacts
        NP        = arts.get("NUMERIC_PROPERTIES", [])
        ntypes    = list(arts.get("node_types", []))
        mm        = arts.get("numeric_minmax", {})
        NW        = arts.get("NUMERIC_PROPERTIES_WEIGHTS", {})
        NF_W      = arts.get("NUMERIC_FEATURE_WEIGHT", 1.0)

        # Try to get feature importances / coefficients from the classifier
        coefs = None
        try:
            clf = self.classifier
            c   = getattr(clf, "coef_", None)
            if c is not None and len(c) > 0:
                coefs = c[0]
            else:
                fi = getattr(clf, "feature_importances_", None)
                if fi is not None and len(fi) > 0:
                    coefs = fi
        except Exception:
            pass

        impacts: List[str] = []
        for prop in NP:
            if prop not in ctx:
                continue
            try:
                raw_val = float(ctx[prop])
            except (ValueError, TypeError):
                continue
            if coefs is not None:
                idx = 4 + len(ntypes) + NP.index(prop)
                if idx < len(coefs):
                    lo, hi = mm.get(prop, (0.0, 1.0))
                    normed = max(0.0, min((raw_val - lo) / (hi - lo + 1e-9), 1.0))
                    imp    = float(coefs[idx]) * normed * NW.get(prop, 1.0) * NF_W
                    impacts.append(f"{prop}={raw_val} (impact={imp:.4f})")
                    continue
            impacts.append(f"{prop}={raw_val}")

        ntype = ctx.get("type", "")
        if ntype:
            if coefs is not None and str(ntype) in ntypes:
                idx = 4 + ntypes.index(str(ntype))
                if idx < len(coefs):
                    impacts.append(f"type='{ntype}' (impact={float(coefs[idx]):.4f})")
                    ntype = ""  # already added
            if ntype:
                impacts.append(f"type='{ntype}'")

        if not impacts:
            return ""
        has_real = any("impact=" in s and "impact=0.0000" not in s for s in impacts)
        prefix   = "contributed mathematically to" if has_real else "was evaluated but had no significant impact on"
        return f"The node context ({', '.join(impacts)}) {prefix} this neural recommendation."


# =============================================================================
# 21.  TASK 4 — BUNDLE CONSTRUCTION & EXPORT
# =============================================================================

def _build_full_bundle(
    path_engine: OntologyPathEngine,
    explanation_engine: ExplanationEngine,
    df_out: pd.DataFrame,
    meta: dict,
    cfg: PipelineConfig,
) -> NSXAIInferenceBundle:
    """Load Task 2/3 artifacts and assemble NSXAIInferenceBundle."""
    import joblib

    clf_path  = os.path.join(cfg.output_dir, "best_classifier.pkl")
    arts_path = os.path.join(cfg.output_dir, "inference_artifacts.pkl")
    sym_path  = os.path.join(cfg.t3_dir, "sym_config.pkl")

    classifier        = None
    feature_artifacts = {}
    sym_config        = {}

    if os.path.exists(clf_path):
        try:
            classifier = joblib.load(clf_path)
            log.info("Classifier loaded: %s", clf_path)
        except Exception as e:
            log.warning("Could not load classifier: %s", e)
    else:
        log.warning("best_classifier.pkl not found → cold-start disabled.")

    if os.path.exists(arts_path):
        try:
            with open(arts_path, "rb") as f:
                feature_artifacts = pickle.load(f)
            # Approximate graph_means/stds if no scaler
            if "scaler" not in feature_artifacts:
                xn = feature_artifacts.get("X_nodes_np")
                if xn is not None and xn.shape[1] >= 4:
                    feature_artifacts["graph_means"] = xn[:, :4].mean(0).tolist()
                    feature_artifacts["graph_stds"]  = xn[:, :4].std(0).tolist()
        except Exception as e:
            log.warning("Could not load feature artifacts: %s", e)
    else:
        log.warning("inference_artifacts.pkl not found → cold-start disabled.")

    if os.path.exists(sym_path):
        try:
            with open(sym_path, "rb") as f:
                sym_config = pickle.load(f)
        except Exception as e:
            log.warning("Could not load sym_config: %s", e)

    bundle = NSXAIInferenceBundle(
        path_engine=path_engine,
        explanation_engine=explanation_engine,
        topk_df=df_out,
        meta={**meta, "cold_start_enabled": classifier is not None},
        classifier=classifier,
        feature_artifacts=feature_artifacts,
        sym_config=sym_config,
    )

    # Single save point for the full bundle
    full_path = os.path.join(cfg.t4_dir, "nsxai_full_bundle.pkl")
    bundle.save(full_path)
    log.info("NSXAIInferenceBundle → %s | cold_start=%s", full_path, bundle.can_infer_new())
    return bundle


def make_visualizations_task4(df_out: pd.DataFrame, cfg: PipelineConfig) -> None:
    """Generate Task 4 summary figures (3 PNG files)."""
    output_dir = cfg.t4_dir
    color_map  = {"High": "#3EC97C", "Moderate": "#F4A44A", "Weak": "#EF6B5B"}

    # Fig 1: Overview
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    fig.suptitle("Task 4 — Explanation Layer Overview", fontsize=13, fontweight="bold", y=1.01)

    lc = df_out["confidence_label"].value_counts()
    axes[0].pie(
        lc.values, labels=lc.index,
        colors=[color_map.get(l, "#aaa") for l in lc.index],
        autopct="%1.1f%%", startangle=140,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    axes[0].set_title("Confidence Label Distribution", fontweight="bold")

    dc = df_out["path_distance"].value_counts().sort_index()
    axes[1].bar(
        dc.index.astype(str), dc.values,
        color=["#3EC97C" if d == 1 else "#5B8DEF" for d in dc.index], edgecolor="white",
    )
    axes[1].set_title("Ontology Path Distance", fontweight="bold")
    for i, (k, v) in enumerate(dc.items()):
        axes[1].text(i, v + 0.1, str(v), ha="center", fontsize=10, fontweight="bold")

    nc = df_out["known_positive"].value_counts()
    axes[2].bar(
        ["Novel", "Validated"], [nc.get(False, 0), nc.get(True, 0)],
        color=["#5B8DEF", "#3EC97C"], edgecolor="white",
    )
    axes[2].set_title("Novel vs Validated", fontweight="bold")
    for i, v in enumerate([nc.get(False, 0), nc.get(True, 0)]):
        axes[2].text(i, v + 0.1, str(v), ha="center", fontsize=10, fontweight="bold")

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "fig_task4_overview.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # Fig 2: Heatmap
    try:
        pivot = df_out.pivot_table(
            index="source", columns="target",
            values="neurosymbolic_score", aggfunc="max",
        ).fillna(0)
        nr, nc_ = len(pivot.index), len(pivot.columns)
        fig2, ax2 = plt.subplots(figsize=(max(10, nc_ * 0.9 + 3), max(5, nr * 0.45 + 2)))
        im = ax2.imshow(pivot.values, aspect="auto", cmap="YlGn", vmin=0, vmax=1)
        ax2.set_xticks(range(nc_)); ax2.set_xticklabels(pivot.columns, rotation=30, ha="right", fontsize=9)
        ax2.set_yticks(range(nr));  ax2.set_yticklabels(pivot.index, fontsize=9)
        for i in range(nr):
            for j in range(nc_):
                v = pivot.values[i, j]
                if v > 0:
                    ax2.text(j, i, f"{v:.2f}", ha="center", va="center",
                             fontsize=7.5, color="white" if v >= 0.70 else "black")
        plt.colorbar(im, ax=ax2, shrink=0.8, label="NS Score")
        ax2.set_title("Neuro-Symbolic Score — Source × Target", fontsize=12, fontweight="bold")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "fig_task4_score_heatmap.png"), dpi=150, bbox_inches="tight")
        plt.close(fig2)
    except Exception as e:
        log.warning("Heatmap skipped: %s", e)

    # Fig 3: Explanation quality
    if "explanation" in df_out.columns:
        dq = df_out.copy()
        dq["exp_length"] = dq["explanation"].astype(str).str.len()
        fig3, ax3 = plt.subplots(1, 2, figsize=(13, 5))
        fig3.suptitle("Explanation Quality Metrics", fontsize=12, fontweight="bold", y=1.01)
        for lbl, grp in dq.groupby("confidence_label"):
            ax3[0].hist(grp["exp_length"], bins=15, alpha=0.6, label=lbl, color=color_map.get(lbl, "#aaa"))
        ax3[0].set_xlabel("Explanation length (chars)")
        ax3[0].set_title("Length by Confidence Level", fontweight="bold")
        ax3[0].legend()
        valid = dq[dq["path_distance"] > 0]
        if not valid.empty:
            dg = valid.groupby("path_distance")["neurosymbolic_score"].agg(["mean", "std", "count"]).reset_index()
            ax3[1].errorbar(dg["path_distance"], dg["mean"], yerr=dg["std"],
                            fmt="o-", color="#2EC4B6", linewidth=2, markersize=8, capsize=4)
            for _, r in dg.iterrows():
                ax3[1].text(r["path_distance"], r["mean"] + 0.01, f"n={int(r['count'])}", ha="center", fontsize=8)
        ax3[1].set_xlabel("Path distance (steps)")
        ax3[1].set_title("Score vs Ontological Distance", fontweight="bold")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "fig_task4_explanation_quality.png"), dpi=150, bbox_inches="tight")
        plt.close(fig3)

    log.info("Task 4 visualisations → %s/", output_dir)


def export_all(
    df_out: pd.DataFrame,
    bundle: NSXAIInferenceBundle,
    cfg: PipelineConfig,
) -> Dict[str, str]:
    """
    Export all Task 4 deliverables. Returns {name → path} mapping.
    NOTE: The bundle has already been saved by _build_full_bundle; here we
    only write the CSV/JSON files and a lightweight Task4Bundle copy.
    """
    output_dir = cfg.t4_dir
    paths: Dict[str, str] = {}

    # Full CSV
    out_cols   = [c for c in OUTPUT_COLS if c in df_out.columns]
    extra_cols = [c for c in df_out.columns if c not in out_cols]
    p = os.path.join(output_dir, "task4_explanations.csv")
    df_out[out_cols + extra_cols].to_csv(p, index=False)
    paths["explanations_csv"] = p

    # Human-readable CSV
    human_cols = ["source", "target", "neurosymbolic_score", "confidence_label",
                  "path_distance", "known_positive", "ontology_path", "explanation"]
    p = os.path.join(output_dir, "task4_topk_human_readable.csv")
    df_out[[c for c in human_cols if c in df_out.columns]].to_csv(p, index=False)
    paths["human_readable_csv"] = p

    # Inference payload JSON
    payload = []
    for src in bundle.list_sources():
        payload.append({
            "mode": "known_source", "source": src, "top_k": 5,
            "example_response": bundle.predict(src, top_k=3),
        })
    if bundle.can_infer_new():
        payload.append({
            "mode": "cold_start", "node_name": "__new_node_example__",
            "node_context": {"type": "unknown"}, "top_k": 3,
            "example_response": bundle.predict_new(
                "__new_node_example__", {"type": "unknown", "in_degree": 0}, top_k=3
            ),
        })
    p = os.path.join(output_dir, "task4_inference_payload.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    paths["inference_payload_json"] = p

    # Lightweight Task4Bundle (no classifier)
    p = os.path.join(output_dir, "task4_model_bundle.pkl")
    Task4Bundle(
        path_engine=bundle.path_engine,
        explanation_engine=bundle.explanation_engine,
        topk_df=bundle.topk_df,
        meta=bundle.meta,
    ).save(p)
    paths["bundle_pkl"] = p

    # Full bundle path (already written by _build_full_bundle)
    paths["nsxai_bundle_pkl"] = os.path.join(output_dir, "nsxai_full_bundle.pkl")

    # API schema
    p = os.path.join(output_dir, "task4_model_bundle_schema.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(bundle.schema(), f, indent=2, ensure_ascii=False)
    paths["schema_json"] = p

    # Visualisations
    make_visualizations_task4(df_out, cfg)
    for fig_name in ("fig_task4_overview.png", "fig_task4_score_heatmap.png",
                     "fig_task4_explanation_quality.png"):
        fp = os.path.join(output_dir, fig_name)
        if os.path.exists(fp):
            paths[fig_name] = fp

    log.info("Task 4 exports: %d files → %s/", len(paths), output_dir)
    return paths


# =============================================================================
# 22.  TASK 4 — ENTRY POINT
# =============================================================================

def run_task4(
    topk_df: pd.DataFrame,
    graph: nx.DiGraph,
    cfg: PipelineConfig,
    target_descriptions: Optional[Dict[str, str]] = None,
    extra_block_fn: Optional[Callable] = None,
) -> Tuple[pd.DataFrame, NSXAIInferenceBundle, Dict[str, str]]:
    """
    Main entry point for Task 4: explanation generation + deployment bundle.

    Parameters
    ----------
    topk_df  : Top-K recommendations DataFrame from Task 3.
    graph    : Knowledge graph (G_sym from Task 3).
    cfg      : Pipeline configuration.
    target_descriptions : Optional {target_id → description} overrides.
    extra_block_fn      : Optional fn(row, path_stats) → str for custom block.

    Returns
    -------
    (df_out, bundle, export_paths)
    """
    log.info("=" * 62)
    log.info("  TASK 4 — LAYER 5: EXPLANATION GENERATION + DEPLOYMENT")
    log.info("=" * 62)

    # Ensure required columns with defaults
    missing = REQUIRED_T3_COLS - set(topk_df.columns)
    if missing:
        log.warning("Missing T3 columns (defaulted): %s", missing)
        for col in missing:
            topk_df[col] = 0.0 if col in ("symbolic_confidence", "probability_mean", "neurosymbolic_score") else False

    # Engines
    path_engine        = OntologyPathEngine(graph)
    explanation_engine = ExplanationEngine(
        path_engine=path_engine,
        cfg=cfg,
        target_descriptions=target_descriptions or {},
        extra_block_fn=extra_block_fn,
    )

    # Explanations
    log.info("Generating explanations for %d pairs…", len(topk_df))
    df_out = explanation_engine.generate_all(topk_df)
    log.info("Done: %d rows.", len(df_out))

    # Bundle (single save in _build_full_bundle)
    meta = {
        "n_sources":    df_out["source"].nunique(),
        "n_targets":    df_out["target"].nunique(),
        "graph_nodes":  graph.number_of_nodes(),
        "graph_edges":  graph.number_of_edges(),
        "source_label": cfg.source_label,
        "target_label": cfg.target_label,
    }
    bundle = _build_full_bundle(path_engine, explanation_engine, df_out, meta, cfg)

    # Sanity checks
    sample_src = df_out["source"].iloc[0]
    res        = bundle.predict(sample_src, top_k=2)
    assert isinstance(res, list), "predict() must return a list."
    log.info("predict() OK: %d result(s) for '%s'.", len(res), sample_src)

    if bundle.can_infer_new():
        cs = bundle.predict_new("__test__", {"type": "unknown"}, top_k=2)
        log.info("Cold-start OK: %d result(s).", len(cs))
    else:
        log.warning("Cold-start disabled (classifier absent).")

    # Exports (no re-save of bundle here)
    export_paths = export_all(df_out, bundle, cfg)

    log.info(
        "Task 4 complete. %d explanations | %d sources | cold-start: %s.",
        len(df_out), df_out["source"].nunique(),
        "YES" if bundle.can_infer_new() else "NO",
    )
    return df_out, bundle, export_paths


# =============================================================================
# 23.  FASTAPI APPLICATION (OPTIONAL)
# =============================================================================

def make_fastapi_app(bundle_path: str):
    """
    Build a FastAPI application exposing the NSXAI inference bundle.

    Usage::

        app = make_fastapi_app("outputs/task4/nsxai_full_bundle.pkl")
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)

    Returns None if FastAPI is not installed.
    """
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel
    except ImportError:
        log.warning("FastAPI not installed: pip install fastapi uvicorn")
        return None

    _b  = NSXAIInferenceBundle.load(bundle_path)
    app = FastAPI(
        title="NSXAI — Neuro-Symbolic Recommendation API",
        version=NSXAIInferenceBundle.VERSION,
    )

    class PredictReq(BaseModel):
        source: str
        target: Optional[str] = None
        top_k: int = 5

    class PredictNewReq(BaseModel):
        node_name: str
        node_context: Optional[dict] = None
        top_k: int = 5

    class ContrastiveReq(BaseModel):
        source: str; target_a: str; target_b: str

    @app.get("/health")
    def health():
        return JSONResponse({
            "status": "ok", "version": _b.meta.get("version"),
            "n_recommendations": _b.meta.get("n_recommendations"),
            "cold_start": _b.can_infer_new(),
        })

    @app.get("/sources")
    def sources(): return JSONResponse(_b.list_sources())

    @app.get("/targets")
    def targets(): return JSONResponse(_b.list_targets())

    @app.get("/schema")
    def schema(): return JSONResponse(_b.schema())

    from fastapi import Body

    @app.post("/predict")
    def predict(req: dict = Body(...)):
        return JSONResponse(_b.predict(req["source"], req.get("target"), req.get("top_k", 5)))

    @app.post("/predict_new")
    def predict_new(req: dict = Body(...)):
        if not _b.can_infer_new():
            return JSONResponse({"error": "cold-start disabled"}, status_code=503)
        return JSONResponse(_b.predict_new(req["node_name"], req.get("node_context"), req.get("top_k", 5)))

    @app.post("/contrastive")
    def contrastive(req: dict = Body(...)):
        return JSONResponse({"explanation": _b.explain_contrastive(req["source"], req["target_a"], req["target_b"])})

    return app


# =============================================================================
# 24.  FULL PIPELINE RUNNER
# =============================================================================

def run_pipeline(cfg: PipelineConfig) -> dict:
    """
    Run the complete Tasks 2 → 3 → 4 pipeline from a PipelineConfig.

    Returns a dict with keys: t2, t3, df_task4, bundle, export_paths.
    """
    log.info("Device: %s | Output: %s/", cfg.device, cfg.output_dir)
    log.info("Numeric properties: %s", cfg.numeric.properties)

    nodes, edges, numeric_raw_df = load_ontology(cfg.ontology_path, cfg)

    t2 = run_task2(nodes, edges, numeric_raw_df, cfg)
    plot_numeric_vs_probability(t2["agg_reco_df"], cfg)
    plot_numeric_property_summary(t2["N"], numeric_raw_df, cfg)

    t3 = run_task3(t2, cfg)

    df4, bundle, paths = run_task4(t3["df_topk"], t3["G_sym"], cfg)

    log.info("Pipeline complete. All outputs in %s/", cfg.output_dir)
    return dict(t2=t2, t3=t3, df_task4=df4, bundle=bundle, export_paths=paths)


# =============================================================================
# 25.  MAIN
# =============================================================================

def main() -> None:
    """
    Entry point — run with default config or customise PipelineConfig first.

    Example::

        cfg = PipelineConfig(
            ontology_path = "my_ontology.csv",
            output_dir    = "outputs",
            target_types  = ["MyTargetClass"],
            source_label  = "topic",
            target_label  = "resource",
        )
        results = run_pipeline(cfg)
    """
    cfg = PipelineConfig(
        ontology_path = "ontology_matrix.csv",
        output_dir    = "outputs/task2_multimodel",
        target_types  = ["GameElementResource"],
        source_label  = "topic",
        target_label  = "game element",
    )
    run_pipeline(cfg)


if __name__ == "__main__":
    main()