"""Cross-modal conversion tools for DIGIMON.

Convert between graph, table, and vector representations so agents can analyze
data in whichever modality best fits the question.

Conversion paths:
  graph → table: nodes, edges, adjacency
  table → graph: entity_rel, adjacency, auto
  graph → vector: node_embed, features
  table → vector: stats, row_embed
  vector → graph: similarity, clustering
  vector → table: direct, pca, similarity
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Optional, Protocol, runtime_checkable

import networkx as nx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Graph adapter — reuses pattern from graph_analysis_tools.py
# =============================================================================

def _extract_networkx_graph(graph_instance: Any) -> Optional[nx.Graph]:
    """Get the raw NetworkX graph from a DIGIMON graph instance."""
    if hasattr(graph_instance, "_graph"):
        storage = graph_instance._graph
        if hasattr(storage, "graph"):
            return storage.graph
        elif hasattr(storage, "_graph"):
            return storage._graph
        elif isinstance(storage, nx.Graph):
            return storage
    elif hasattr(graph_instance, "graph"):
        return graph_instance.graph
    elif isinstance(graph_instance, nx.Graph):
        return graph_instance
    return None


def _graph_to_dict(nx_graph: nx.Graph) -> dict[str, list[dict]]:
    """Convert NetworkX graph to the intermediate dict format.

    Returns:
        {nodes: [{id, label, type, properties}],
         edges: [{source, target, type, weight, properties}]}
    """
    nodes = []
    for node_id, data in nx_graph.nodes(data=True):
        node = {
            "id": str(node_id),
            "label": data.get("label", data.get("entity_name", str(node_id))),
            "type": data.get("entity_type", data.get("type", "entity")),
            "properties": {k: _safe_serialize(v) for k, v in data.items()
                          if k not in ("label", "entity_name", "entity_type", "type")},
        }
        nodes.append(node)

    edges = []
    for src, tgt, data in nx_graph.edges(data=True):
        edge = {
            "source": str(src),
            "target": str(tgt),
            "type": data.get("relation_type", data.get("label", "related_to")),
            "weight": float(data.get("weight", 1.0)),
            "properties": {k: _safe_serialize(v) for k, v in data.items()
                          if k not in ("relation_type", "label", "weight")},
        }
        edges.append(edge)

    return {"nodes": nodes, "edges": edges}


def _dict_to_networkx(graph_dict: dict[str, list[dict]]) -> nx.Graph:
    """Convert intermediate dict back to a NetworkX graph."""
    G = nx.Graph()
    for node in graph_dict.get("nodes", []):
        props = dict(node.get("properties", {}))
        props["label"] = node.get("label", node["id"])
        props["entity_type"] = node.get("type", "entity")
        G.add_node(node["id"], **props)
    for edge in graph_dict.get("edges", []):
        props = dict(edge.get("properties", {}))
        props["relation_type"] = edge.get("type", "related_to")
        props["weight"] = edge.get("weight", 1.0)
        G.add_edge(edge["source"], edge["target"], **props)
    return G


# =============================================================================
# Embedding providers
# =============================================================================

@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> np.ndarray: ...


class HashEmbeddingProvider:
    """Deterministic hash-based fallback. No model needed. For testing only.

    Uses text hash as PRNG seed to generate a reproducible unit vector.
    """

    def __init__(self, dim: int = 64):
        self.dim = dim

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        result = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            # Use hash as seed for deterministic random vector
            seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**31)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self.dim).astype(np.float32)
            norm = np.linalg.norm(vec)
            result[i] = vec / norm  # randn never produces all-zeros
        return result


class LocalEmbeddingProvider:
    """sentence-transformers (all-MiniLM-L6-v2, 384D). Free, fast, local."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        self._load()
        return self._model.encode(texts, normalize_embeddings=True)


class DigimonEmbeddingProvider:
    """Wraps _state['encoder'] from DIGIMON config."""

    def __init__(self, encoder: Any):
        self._encoder = encoder

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        embeddings = []
        for text in texts:
            emb = await self._encoder.aembed_query(text)
            embeddings.append(emb)
        return np.array(embeddings, dtype=np.float32)


def get_embedding_provider(
    provider_name: str, state: Optional[dict] = None,
) -> EmbeddingProvider:
    """Factory for embedding providers."""
    if provider_name == "hash":
        return HashEmbeddingProvider()
    elif provider_name == "digimon":
        if state and "encoder" in state:
            return DigimonEmbeddingProvider(state["encoder"])
        raise ValueError("Digimon encoder not available in state")
    elif provider_name == "local":
        return LocalEmbeddingProvider()
    else:
        raise ValueError(f"Unknown embedding provider: {provider_name!r}")


# =============================================================================
# Graph → Table conversions
# =============================================================================

def graph_to_table_nodes(graph_dict: dict) -> pd.DataFrame:
    """Flatten node properties to columns."""
    rows = []
    for node in graph_dict["nodes"]:
        row = {"node_id": node["id"], "label": node["label"], "type": node["type"]}
        row.update(node.get("properties", {}))
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["node_id", "label", "type"])


def graph_to_table_edges(graph_dict: dict) -> pd.DataFrame:
    """Each edge becomes a row, properties become columns."""
    rows = []
    for edge in graph_dict["edges"]:
        row = {
            "source": edge["source"],
            "target": edge["target"],
            "type": edge["type"],
            "weight": edge["weight"],
        }
        row.update(edge.get("properties", {}))
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["source", "target", "type", "weight"])


def graph_to_table_adjacency(graph_dict: dict) -> pd.DataFrame:
    """Build NxN weight matrix as DataFrame."""
    node_ids = [n["id"] for n in graph_dict["nodes"]]
    n = len(node_ids)
    matrix = np.zeros((n, n), dtype=np.float64)
    idx = {nid: i for i, nid in enumerate(node_ids)}
    for edge in graph_dict["edges"]:
        i = idx.get(edge["source"])
        j = idx.get(edge["target"])
        if i is not None and j is not None:
            matrix[i, j] = edge["weight"]
            matrix[j, i] = edge["weight"]  # symmetric for undirected
    return pd.DataFrame(matrix, index=node_ids, columns=node_ids)


# =============================================================================
# Table → Graph conversions
# =============================================================================

def table_to_graph_entity_rel(
    df: pd.DataFrame,
    source_col: Optional[str] = None,
    target_col: Optional[str] = None,
    type_col: Optional[str] = None,
) -> dict[str, list[dict]]:
    """Detect source/target columns, build nodes+edges."""
    # Auto-detect columns if not specified
    if source_col is None or target_col is None:
        source_col, target_col = _detect_entity_columns(df)

    nodes_set: dict[str, dict] = {}
    edges = []

    for _, row in df.iterrows():
        src = str(row[source_col])
        tgt = str(row[target_col])
        if src not in nodes_set:
            nodes_set[src] = {"id": src, "label": src, "type": "entity", "properties": {}}
        if tgt not in nodes_set:
            nodes_set[tgt] = {"id": tgt, "label": tgt, "type": "entity", "properties": {}}

        if type_col and type_col not in df.columns:
            raise ValueError(f"type_col {type_col!r} not found in DataFrame columns: {list(df.columns)}")
        rel_type = str(row[type_col]) if type_col else "related_to"
        props = {k: _safe_serialize(v) for k, v in row.items()
                 if k not in (source_col, target_col, type_col)}
        edges.append({
            "source": src, "target": tgt, "type": rel_type,
            "weight": float(row.get("weight", 1.0)) if "weight" in df.columns else 1.0,
            "properties": props,
        })

    return {"nodes": list(nodes_set.values()), "edges": edges}


def table_to_graph_adjacency(df: pd.DataFrame) -> dict[str, list[dict]]:
    """Non-zero cells in a square matrix become edges."""
    node_ids = [str(c) for c in df.columns]
    nodes = [{"id": nid, "label": nid, "type": "entity", "properties": {}} for nid in node_ids]
    edges = []
    matrix = df.values
    for i in range(len(node_ids)):
        for j in range(i + 1, len(node_ids)):
            w = float(matrix[i, j])
            if w != 0.0:
                edges.append({
                    "source": node_ids[i], "target": node_ids[j],
                    "type": "related_to", "weight": w, "properties": {},
                })
    return {"nodes": nodes, "edges": edges}


def table_to_graph_auto(df: pd.DataFrame) -> dict[str, list[dict]]:
    """Heuristic: if square and all-numeric, treat as adjacency; else entity_rel."""
    if df.shape[0] == df.shape[1] and df.dtypes.apply(lambda d: np.issubdtype(d, np.number)).all():
        return table_to_graph_adjacency(df)
    return table_to_graph_entity_rel(df)


def _detect_entity_columns(df: pd.DataFrame) -> tuple[str, str]:
    """Heuristic: find two string columns with high uniqueness ratio."""
    string_cols = [c for c in df.columns if df[c].dtype == object]
    # Prefer columns named source/target, from/to, subject/object
    preferred_pairs = [
        ("source", "target"), ("from", "to"), ("subject", "object"),
        ("src", "dst"), ("head", "tail"), ("entity1", "entity2"),
    ]
    lower_cols = {c.lower(): c for c in string_cols}
    for src_name, tgt_name in preferred_pairs:
        if src_name in lower_cols and tgt_name in lower_cols:
            return lower_cols[src_name], lower_cols[tgt_name]

    # Fallback: pick two string columns with highest uniqueness ratio
    scored = []
    for c in string_cols:
        ratio = df[c].nunique() / len(df) if len(df) > 0 else 0
        scored.append((ratio, c))
    scored.sort(reverse=True)
    if len(scored) >= 2:
        return scored[0][1], scored[1][1]
    if len(scored) == 1:
        logger.warning(
            f"Only one string column ({scored[0][1]!r}) found — using it for both source and target. "
            f"This will create self-loop edges. Consider specifying source_col/target_col explicitly."
        )
        return scored[0][1], scored[0][1]
    raise ValueError(
        f"Cannot detect entity columns. Available columns: {list(df.columns)}. "
        f"Specify source_col and target_col explicitly."
    )


def _safe_serialize(v: Any) -> Any:
    """Make a value JSON-safe."""
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return str(v)


# =============================================================================
# Graph → Vector conversions
# =============================================================================

async def graph_to_vector_node_embed(
    graph_dict: dict, provider: EmbeddingProvider,
) -> np.ndarray:
    """Embed node text (label + type + property values)."""
    texts = []
    for node in graph_dict["nodes"]:
        parts = [node["label"], node["type"]]
        for k, v in node.get("properties", {}).items():
            if isinstance(v, str) and v:
                parts.append(f"{k}: {v}")
        texts.append(" | ".join(parts))

    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    return await provider.embed_texts(texts)


def graph_to_vector_features(graph_dict: dict) -> np.ndarray:
    """Static graph statistics as a 1x10 feature vector."""
    nodes = graph_dict["nodes"]
    edges = graph_dict["edges"]
    n_nodes = len(nodes)
    n_edges = len(edges)

    # Degree distribution
    degree: dict[str, int] = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    degrees = list(degree.values()) if degree else [0]

    # Type diversity
    node_types = len({n["type"] for n in nodes})
    edge_types = len({e["type"] for e in edges})

    weights = [e["weight"] for e in edges] if edges else [0.0]

    features = np.array([
        n_nodes,
        n_edges,
        n_edges / n_nodes if n_nodes > 0 else 0,  # density proxy
        np.mean(degrees),
        np.std(degrees),
        max(degrees),
        node_types,
        edge_types,
        np.mean(weights),
        np.std(weights),
    ], dtype=np.float32).reshape(1, -1)
    return features


# =============================================================================
# Table → Vector conversions
# =============================================================================

def table_to_vector_stats(df: pd.DataFrame) -> np.ndarray:
    """Descriptive statistics as a 1x11 feature vector."""
    numeric_cols = df.select_dtypes(include=[np.number])
    string_cols = df.select_dtypes(include=[object])

    nv = numeric_cols.values
    stats = np.array([
        df.shape[0],                                        # row_count
        df.shape[1],                                        # col_count
        int(df.isnull().sum().sum()),                       # null_count
        len(numeric_cols.columns),                          # numeric_cols
        len(string_cols.columns),                           # string_cols
        float(np.nanmean(nv)) if nv.size > 0 else 0.0,
        float(np.nanstd(nv)) if nv.size > 0 else 0.0,
        float(np.nanmin(nv)) if nv.size > 0 else 0.0,
        float(np.nanmax(nv)) if nv.size > 0 else 0.0,
        float(df.nunique().mean()),                         # avg unique per col
        float(df.duplicated().sum()),                       # duplicate rows
    ], dtype=np.float32).reshape(1, -1)
    return stats


async def table_to_vector_row_embed(
    df: pd.DataFrame, provider: EmbeddingProvider,
) -> np.ndarray:
    """Embed each row as text 'col: value | col: value | ...'."""
    texts = []
    for _, row in df.iterrows():
        parts = [f"{col}: {row[col]}" for col in df.columns if pd.notna(row[col])]
        texts.append(" | ".join(parts))
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    return await provider.embed_texts(texts)


# =============================================================================
# Vector → Graph conversions
# =============================================================================

def vector_to_graph_similarity(
    vectors: np.ndarray,
    threshold: float = 0.5,
    labels: Optional[list[str]] = None,
) -> dict[str, list[dict]]:
    """Pairwise cosine similarity, threshold → edges."""
    from sklearn.metrics.pairwise import cosine_similarity

    n = vectors.shape[0]
    if labels is None:
        labels = [f"vec_{i}" for i in range(n)]

    sim_matrix = cosine_similarity(vectors)
    nodes = [
        {"id": labels[i], "label": labels[i], "type": "vector_node", "properties": {}}
        for i in range(n)
    ]
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                edges.append({
                    "source": labels[i], "target": labels[j],
                    "type": "similar_to", "weight": sim, "properties": {},
                })
    return {"nodes": nodes, "edges": edges}


def vector_to_graph_clustering(
    vectors: np.ndarray,
    method: str = "kmeans",
    n_clusters: int = 5,
    labels: Optional[list[str]] = None,
) -> dict[str, list[dict]]:
    """KMeans or DBSCAN → cluster membership edges."""
    n = vectors.shape[0]
    if labels is None:
        labels = [f"vec_{i}" for i in range(n)]

    if method == "dbscan":
        from sklearn.cluster import DBSCAN
        cluster_labels = DBSCAN(eps=0.5, min_samples=2).fit_predict(vectors)
    else:
        from sklearn.cluster import KMeans
        k = min(n_clusters, n)
        cluster_labels = KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(vectors)

    # Build nodes for data points
    nodes = [
        {"id": labels[i], "label": labels[i], "type": "data_point", "properties": {}}
        for i in range(n)
    ]
    # Build nodes for clusters
    unique_clusters = set(int(c) for c in cluster_labels if c >= 0)
    for c in unique_clusters:
        nodes.append({
            "id": f"cluster_{c}", "label": f"Cluster {c}",
            "type": "cluster", "properties": {},
        })

    # Edges: data point → cluster
    edges = []
    for i in range(n):
        c = int(cluster_labels[i])
        if c >= 0:
            edges.append({
                "source": labels[i], "target": f"cluster_{c}",
                "type": "belongs_to", "weight": 1.0, "properties": {},
            })

    return {"nodes": nodes, "edges": edges}


# =============================================================================
# Vector → Table conversions
# =============================================================================

def _validate_2d(vectors: np.ndarray, caller: str) -> tuple[int, int]:
    """Validate vectors is a 2D array, return (n_rows, n_dims)."""
    if vectors.ndim != 2:
        raise ValueError(f"{caller}: expected 2D array, got shape {vectors.shape}")
    return vectors.shape


def vector_to_table_direct(
    vectors: np.ndarray, labels: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Reshape vectors to DataFrame with feature columns + stats."""
    n, d = _validate_2d(vectors, "vector_to_table_direct")
    if labels is None:
        labels = [f"vec_{i}" for i in range(n)]
    cols = [f"dim_{i}" for i in range(d)]
    df = pd.DataFrame(vectors, columns=cols)
    df.insert(0, "id", labels)
    df["norm"] = np.linalg.norm(vectors, axis=1)
    df["mean"] = np.mean(vectors, axis=1)
    df["std"] = np.std(vectors, axis=1)
    return df


def vector_to_table_pca(
    vectors: np.ndarray,
    n_components: int = 10,
    labels: Optional[list[str]] = None,
) -> pd.DataFrame:
    """PCA reduction + metadata."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    n, d = _validate_2d(vectors, "vector_to_table_pca")
    if n < 2:
        raise ValueError(f"vector_to_table_pca: need at least 2 rows for PCA, got {n}")
    nc = min(n_components, n, d)
    if labels is None:
        labels = [f"vec_{i}" for i in range(n)]

    scaled = StandardScaler().fit_transform(vectors)
    pca = PCA(n_components=nc, random_state=42)
    reduced = pca.fit_transform(scaled)

    cols = [f"pc_{i}" for i in range(nc)]
    df = pd.DataFrame(reduced, columns=cols)
    df.insert(0, "id", labels)
    df["explained_variance"] = [sum(pca.explained_variance_ratio_)] * n
    df["norm"] = np.linalg.norm(vectors, axis=1)
    return df


def vector_to_table_similarity(
    vectors: np.ndarray, labels: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Cosine similarity matrix as NxN DataFrame."""
    from sklearn.metrics.pairwise import cosine_similarity

    n, d = _validate_2d(vectors, "vector_to_table_similarity")
    if labels is None:
        labels = [f"vec_{i}" for i in range(n)]
    sim = cosine_similarity(vectors)
    return pd.DataFrame(sim, index=labels, columns=labels)


# =============================================================================
# Conversion dispatcher
# =============================================================================

# Registry of all conversion paths: (source_format, target_format) → {mode: (func, is_async, needs_embedding)}
CONVERSION_REGISTRY: dict[tuple[str, str], dict[str, tuple]] = {
    ("graph", "table"): {
        "nodes": (graph_to_table_nodes, False, False),
        "edges": (graph_to_table_edges, False, False),
        "adjacency": (graph_to_table_adjacency, False, False),
    },
    ("table", "graph"): {
        "entity_rel": (table_to_graph_entity_rel, False, False),
        "adjacency": (table_to_graph_adjacency, False, False),
        "auto": (table_to_graph_auto, False, False),
    },
    ("graph", "vector"): {
        "node_embed": (graph_to_vector_node_embed, True, True),
        "features": (graph_to_vector_features, False, False),
    },
    ("table", "vector"): {
        "stats": (table_to_vector_stats, False, False),
        "row_embed": (table_to_vector_row_embed, True, True),
    },
    ("vector", "graph"): {
        "similarity": (vector_to_graph_similarity, False, False),
        "clustering": (vector_to_graph_clustering, False, False),
    },
    ("vector", "table"): {
        "direct": (vector_to_table_direct, False, False),
        "pca": (vector_to_table_pca, False, False),
        "similarity": (vector_to_table_similarity, False, False),
    },
}


def _default_mode(source: str, target: str) -> str:
    """Pick the default conversion mode for a format pair."""
    defaults = {
        ("graph", "table"): "edges",
        ("table", "graph"): "auto",
        ("graph", "vector"): "features",
        ("table", "vector"): "stats",
        ("vector", "graph"): "similarity",
        ("vector", "table"): "direct",
    }
    return defaults[(source, target)]


async def convert(
    source_data: Any,
    source_format: str,
    target_format: str,
    mode: str = "auto",
    provider: Optional[EmbeddingProvider] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Main conversion dispatcher.

    Args:
        source_data: graph dict, DataFrame, or ndarray
        source_format: "graph", "table", "vector"
        target_format: "graph", "table", "vector"
        mode: conversion strategy (or "auto" for default)
        provider: embedding provider (required for embed modes)
        **kwargs: passed to the conversion function

    Returns:
        {data: <converted>, format: str, mode: str, shape: tuple, conversion_time_ms: float}
    """
    key = (source_format, target_format)
    if key not in CONVERSION_REGISTRY:
        raise ValueError(
            f"No conversion path from {source_format!r} to {target_format!r}. "
            f"Available: {list(CONVERSION_REGISTRY.keys())}"
        )

    modes = CONVERSION_REGISTRY[key]
    if mode == "auto":
        mode = _default_mode(source_format, target_format)

    if mode not in modes:
        raise ValueError(
            f"Unknown mode {mode!r} for {source_format}→{target_format}. "
            f"Available: {list(modes.keys())}"
        )

    func, is_async, needs_embedding = modes[mode]
    t0 = time.monotonic()

    if needs_embedding:
        if provider is None:
            raise ValueError(f"Mode {mode!r} requires an embedding provider")
        result_data = await func(source_data, provider, **kwargs)
    elif is_async:
        result_data = await func(source_data, **kwargs)
    else:
        result_data = func(source_data, **kwargs)

    elapsed_ms = (time.monotonic() - t0) * 1000

    # Determine shape
    if isinstance(result_data, pd.DataFrame):
        shape = result_data.shape
    elif isinstance(result_data, np.ndarray):
        shape = result_data.shape
    elif isinstance(result_data, dict) and "nodes" in result_data:
        shape = (len(result_data["nodes"]), len(result_data["edges"]))
    else:
        shape = ()

    return {
        "data": result_data,
        "format": target_format,
        "mode": mode,
        "shape": shape,
        "conversion_time_ms": round(elapsed_ms, 2),
    }


# =============================================================================
# Round-trip validation
# =============================================================================

async def validate_round_trip(
    data: Any,
    format_sequence: list[str],
    mode_sequence: Optional[list[str]] = None,
    provider: Optional[EmbeddingProvider] = None,
) -> dict[str, Any]:
    """Convert through a sequence of formats and measure preservation.

    Args:
        data: starting data (graph dict, DataFrame, or ndarray)
        format_sequence: e.g. ["graph", "table", "graph"]
        mode_sequence: optional modes for each conversion step
        provider: embedding provider for vector steps

    Returns:
        {preservation_score, entity_preservation, edge_preservation, warnings, steps}
    """
    if len(format_sequence) < 2:
        raise ValueError("format_sequence must have at least 2 formats")

    if mode_sequence is None:
        mode_sequence = ["auto"] * (len(format_sequence) - 1)
    if len(mode_sequence) != len(format_sequence) - 1:
        raise ValueError("mode_sequence must have exactly len(format_sequence)-1 entries")

    original = data
    original_format = format_sequence[0]
    current = data
    steps = []
    warnings = []

    for i in range(len(format_sequence) - 1):
        src_fmt = format_sequence[i]
        tgt_fmt = format_sequence[i + 1]
        mode = mode_sequence[i]
        try:
            result = await convert(current, src_fmt, tgt_fmt, mode=mode, provider=provider)
            steps.append({
                "from": src_fmt, "to": tgt_fmt, "mode": result["mode"],
                "shape": result["shape"], "time_ms": result["conversion_time_ms"],
            })
            current = result["data"]
        except Exception as e:
            warnings.append(f"Step {i} ({src_fmt}→{tgt_fmt}): {e}")
            return {
                "preservation_score": 0.0,
                "entity_preservation": 0.0,
                "edge_preservation": 0.0,
                "warnings": warnings,
                "steps": steps,
            }

    final = current
    final_format = format_sequence[-1]

    # Measure preservation
    entity_pres = _entity_preservation(original, original_format, final, final_format)
    edge_pres = _edge_preservation(original, original_format, final, final_format)
    score = (entity_pres + edge_pres) / 2.0

    return {
        "preservation_score": round(score, 4),
        "entity_preservation": round(entity_pres, 4),
        "edge_preservation": round(edge_pres, 4),
        "warnings": warnings,
        "steps": steps,
    }


def _entity_preservation(orig: Any, orig_fmt: str, final: Any, final_fmt: str) -> float:
    """Measure entity/node count preservation."""
    orig_count = _count_entities(orig, orig_fmt)
    final_count = _count_entities(final, final_fmt)
    if orig_count == 0:
        return 1.0 if final_count == 0 else 0.0
    return min(final_count / orig_count, orig_count / final_count)


def _edge_preservation(orig: Any, orig_fmt: str, final: Any, final_fmt: str) -> float:
    """Measure edge/relationship count preservation."""
    orig_count = _count_edges(orig, orig_fmt)
    final_count = _count_edges(final, final_fmt)
    if orig_count == 0:
        return 1.0 if final_count == 0 else 0.0
    return min(final_count / orig_count, orig_count / final_count)


def _count_entities(data: Any, fmt: str) -> int:
    if fmt == "graph" and isinstance(data, dict):
        return len(data.get("nodes", []))
    if fmt == "table" and isinstance(data, pd.DataFrame):
        return len(data)
    if fmt == "vector" and isinstance(data, np.ndarray):
        return data.shape[0] if data.ndim >= 1 else 0
    return 0


def _count_edges(data: Any, fmt: str) -> int:
    if fmt == "graph" and isinstance(data, dict):
        return len(data.get("edges", []))
    if fmt == "table" and isinstance(data, pd.DataFrame):
        # Can't determine edges from a table alone
        return len(data)
    if fmt == "vector" and isinstance(data, np.ndarray):
        return 0
    return 0


# =============================================================================
# Serialization helpers for MCP responses
# =============================================================================

def serialize_conversion_result(result: dict[str, Any]) -> dict[str, Any]:
    """Make conversion result JSON-safe for MCP."""
    data = result["data"]
    out = {
        "format": result["format"],
        "mode": result["mode"],
        "shape": list(result["shape"]) if isinstance(result["shape"], tuple) else result["shape"],
        "conversion_time_ms": result["conversion_time_ms"],
    }

    if isinstance(data, pd.DataFrame):
        out["data"] = data.to_dict(orient="records")
        out["columns"] = list(data.columns)
    elif isinstance(data, np.ndarray):
        out["data"] = data.tolist()
    elif isinstance(data, dict) and "nodes" in data:
        out["data"] = data
    else:
        out["data"] = str(data)

    return out


def list_all_conversions() -> list[dict[str, Any]]:
    """List all supported conversion paths with modes and descriptions."""
    descriptions = {
        ("graph", "table", "nodes"): "Flatten node properties to DataFrame columns",
        ("graph", "table", "edges"): "Each edge becomes a row with source/target/type/weight",
        ("graph", "table", "adjacency"): "NxN weight matrix indexed by node IDs",
        ("table", "graph", "entity_rel"): "Detect source/target columns, build nodes+edges",
        ("table", "graph", "adjacency"): "Non-zero cells in square matrix become edges",
        ("table", "graph", "auto"): "Heuristic: square numeric = adjacency, else entity_rel",
        ("graph", "vector", "node_embed"): "Embed node text (label+type+props) via embedding model",
        ("graph", "vector", "features"): "Static graph statistics as 1x10 feature vector",
        ("table", "vector", "stats"): "Descriptive statistics as 1x11 feature vector",
        ("table", "vector", "row_embed"): "Embed each row as text via embedding model",
        ("vector", "graph", "similarity"): "Pairwise cosine similarity above threshold → edges",
        ("vector", "graph", "clustering"): "KMeans/DBSCAN → cluster membership edges",
        ("vector", "table", "direct"): "Reshape vectors to DataFrame with feature columns + stats",
        ("vector", "table", "pca"): "PCA reduction with explained variance metadata",
        ("vector", "table", "similarity"): "Cosine similarity matrix as NxN DataFrame",
    }

    result = []
    for (src, tgt), modes in CONVERSION_REGISTRY.items():
        for mode_name in modes:
            _, is_async, needs_embedding = modes[mode_name]
            result.append({
                "source_format": src,
                "target_format": tgt,
                "mode": mode_name,
                "description": descriptions.get((src, tgt, mode_name), ""),
                "requires_embedding": needs_embedding,
            })
    return result
