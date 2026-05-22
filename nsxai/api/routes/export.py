"""
Routes Export — ML & Graph, optimisé pour entraînement IA
==========================================================
Philosophie :
  - Requêtes SPARQL riches extraient le maximum d'information sémantique en un seul aller-retour
  - Formats épurés : chaque colonne a une raison d'être, rien de superflu
  - Index construits une seule fois par requête groupée (_build_rich_index)
  - Encodage UTF-8 partout, MIME corrects, headers informatifs
"""

from __future__ import annotations

import csv
import io
import json
import logging
import random
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Response
from ..services.fuseki import fuseki_client

logger = logging.getLogger(__name__)

router   = APIRouter(prefix="/api/export/ml",  tags=["export-ml"])
router_g = APIRouter(prefix="/api/export",     tags=["export-graph"])

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _short(uri: str) -> str:
    return uri.split("#")[-1].split("/")[-1]

def _run(sparql: str) -> List[Dict]:
    try:
        return fuseki_client.query(sparql)["results"]["bindings"]
    except Exception as exc:
        logger.error("SPARQL error: %s", exc)
        raise HTTPException(502, f"Fuseki error: {exc}") from exc

def _tsv(rows: List[str], filename: str) -> Response:
    return Response(
        "\n".join(rows).encode("utf-8"),
        media_type="text/tab-separated-values; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Row-Count": str(len(rows) - 1),
        },
    )

def _json_resp(obj: Any, filename: str) -> Response:
    return Response(
        json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _csv_resp(buf: io.StringIO, filename: str, row_count: int) -> Response:
    return Response(
        buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Row-Count": str(row_count),
        },
    )

# ─────────────────────────────────────────────────────────────────────────────
# Requêtes SPARQL enrichies
# ─────────────────────────────────────────────────────────────────────────────

# Triplets IRI uniquement — base de tous les exports ML
_Q_TRIPLES = """
SELECT DISTINCT ?s ?p ?o WHERE {
    ?s ?p ?o .
    FILTER(isIRI(?s) && isIRI(?o))
    FILTER(?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
}
ORDER BY ?s ?p ?o
"""

# Entités enrichies : type(s), label, commentaire, degré sortant/entrant calculés par sous-requêtes
_Q_ENTITIES = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

SELECT DISTINCT
    ?entity
    (GROUP_CONCAT(DISTINCT ?type      ; separator="|") AS ?types)
    (SAMPLE(?labelVal)                                  AS ?label)
    (SAMPLE(?commentVal)                                AS ?comment)
    (SAMPLE(?altLabelVal)                               AS ?altLabel)
    (COUNT(DISTINCT ?out_p)                             AS ?outArity)
    (COUNT(DISTINCT ?in_p)                              AS ?inArity)
WHERE {
    # Au moins un triplet en sujet ou objet
    { ?entity ?out_p ?outObj . FILTER(isIRI(?outObj)) }
    UNION
    { ?inSubj ?in_p ?entity . FILTER(isIRI(?inSubj)) }

    FILTER(isIRI(?entity))

    OPTIONAL { ?entity rdf:type ?type }
    OPTIONAL { ?entity rdfs:label ?labelVal      FILTER(langMatches(lang(?labelVal), "fr") || lang(?labelVal) = "") }
    OPTIONAL { ?entity rdfs:comment ?commentVal  FILTER(langMatches(lang(?commentVal), "fr") || lang(?commentVal) = "") }
    OPTIONAL { ?entity skos:altLabel ?altLabelVal }
}
GROUP BY ?entity
ORDER BY ?entity
"""

# Relations enrichies : domaine, range, label, symétrie/transitivité
_Q_RELATIONS = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>

SELECT DISTINCT
    ?pred
    (SAMPLE(?labelVal)              AS ?label)
    (GROUP_CONCAT(DISTINCT ?domain ; separator="|") AS ?domains)
    (GROUP_CONCAT(DISTINCT ?range  ; separator="|") AS ?ranges)
    (COUNT(DISTINCT ?s)             AS ?usage)
    (IF(EXISTS { ?pred rdf:type owl:SymmetricProperty  }, "true", "false") AS ?symmetric)
    (IF(EXISTS { ?pred rdf:type owl:TransitiveProperty }, "true", "false") AS ?transitive)
    (IF(EXISTS { ?pred rdf:type owl:FunctionalProperty }, "true", "false") AS ?functional)
WHERE {
    ?s ?pred ?o .
    FILTER(isIRI(?s) && isIRI(?o))
    FILTER(?pred != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)

    OPTIONAL { ?pred rdfs:label ?labelVal }
    OPTIONAL { ?pred rdfs:domain ?domain }
    OPTIONAL { ?pred rdfs:range  ?range }
}
GROUP BY ?pred
ORDER BY DESC(?usage)
"""

# Chemins de longueur 2 — contexte de voisinage pour embedding
_Q_PATHS2 = """
SELECT DISTINCT ?s ?p1 ?mid ?p2 ?o WHERE {
    ?s  ?p1  ?mid .
    ?mid ?p2  ?o .
    FILTER(isIRI(?s) && isIRI(?mid) && isIRI(?o))
    FILTER(?p1 != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
    FILTER(?p2 != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
    FILTER(?s != ?o)
}
LIMIT 200000
"""

# Cooccurrences : paires d'entités partageant un type commun (signal de similarité)
_Q_COOC = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?type (COUNT(DISTINCT ?e) AS ?count) (GROUP_CONCAT(DISTINCT ?e ; separator="|") AS ?members)
WHERE {
    ?e rdf:type ?type .
    FILTER(isIRI(?e))
}
GROUP BY ?type
HAVING (COUNT(DISTINCT ?e) > 1)
ORDER BY DESC(?count)
"""

# Attributs littéraux par entité (features numériques / textuelles)
_Q_LITERALS = """
SELECT ?s ?p ?val ?dt WHERE {
    ?s ?p ?val .
    FILTER(isIRI(?s) && isLiteral(?val))
    FILTER(?p != <http://www.w3.org/2000/01/rdf-schema#label>)
    FILTER(?p != <http://www.w3.org/2000/01/rdf-schema#comment>)
    BIND(datatype(?val) AS ?dt)
}
ORDER BY ?s ?p
"""


# ─────────────────────────────────────────────────────────────────────────────
# Index central — construit une fois, partagé entre endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _build_rich_index():
    """
    Retourne (e2i, r2i, triples, entity_meta, rel_meta) en un seul appel groupé.

    entity_meta[uri] = {types, label, out_degree, in_degree, ...}
    rel_meta[uri]    = {label, domains, ranges, usage, flags}
    """
    def _bval(b: Dict, key: str, default: str = "") -> str:
        """Lecture sécurisée d'un binding SPARQL optionnel (clé absente = valeur vide)."""
        return (b.get(key) or {}).get("value", default)

    # --- Entités ---
    entity_meta: Dict[str, Dict] = {}
    for b in _run(_Q_ENTITIES):
        uri       = b["entity"]["value"]
        types_raw = _bval(b, "types")
        types     = [_short(t) for t in types_raw.split("|") if t] if types_raw else []
        entity_meta[uri] = {
            "label":      _bval(b, "label",    _short(uri)),
            "alt_label":  _bval(b, "altLabel", ""),
            "comment":    _bval(b, "comment",  ""),
            "types":      types,
            "type_count": len(types),
            "out_arity":  int(_bval(b, "outArity", "0") or "0"),
            "in_arity":   int(_bval(b, "inArity",  "0") or "0"),
        }

    # --- Relations ---
    rel_meta: Dict[str, Dict] = {}
    for b in _run(_Q_RELATIONS):
        uri         = b["pred"]["value"]
        domains_raw = _bval(b, "domains")
        ranges_raw  = _bval(b, "ranges")
        rel_meta[uri] = {
            "label":      _bval(b, "label", _short(uri)),
            "domains":    [_short(d) for d in domains_raw.split("|") if d] if domains_raw else [],
            "ranges":     [_short(r) for r in ranges_raw.split("|")  if r] if ranges_raw else [],
            "usage":      int(_bval(b, "usage", "0") or "0"),
            "symmetric":  _bval(b, "symmetric")  == "true",
            "transitive": _bval(b, "transitive") == "true",
            "functional": _bval(b, "functional") == "true",
        }

    # --- Triplets + index entier ---
    e2i: Dict[str, int] = {}
    r2i: Dict[str, int] = {}
    triples: List[Tuple[str, str, str]] = []
    seen: set = set()

    for b in _run(_Q_TRIPLES):
        s = b["s"]["value"]
        p = b["p"]["value"]
        o = b["o"]["value"]
        key = (s, p, o)
        if key in seen:
            continue
        seen.add(key)
        for ent in (s, o):
            if ent not in e2i:
                e2i[ent] = len(e2i)
        if p not in r2i:
            r2i[p] = len(r2i)
        triples.append(key)

    return e2i, r2i, triples, entity_meta, rel_meta


# ─────────────────────────────────────────────────────────────────────────────
# ML exports
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/triples.tsv", summary="Triplets symboliques (labels courts)")
async def export_ml_triples() -> Response:
    """
    TSV des triplets IRI-only sous forme symbolique.
    Colonnes : head  rel  tail
    Usage    : pd.read_csv(f, sep='\\t')
    """
    e2i, r2i, triples, _, _ = _build_rich_index()
    rows = ["head\trel\ttail"] + [
        f"{_short(h)}\t{_short(r)}\t{_short(t)}" for h, r, t in triples
    ]
    return _tsv(rows, "triples.tsv")


@router.get("/triples_encoded.tsv", summary="Triplets encodés (indices entiers)")
async def export_ml_encoded() -> Response:
    """
    TSV prêt pour PyKEEN / AmpliGraph / DGL-KE.
    Colonnes : head_id  rel_id  tail_id
    """
    e2i, r2i, triples, _, _ = _build_rich_index()
    rows = ["head_id\trel_id\ttail_id"] + [
        f"{e2i[h]}\t{r2i[r]}\t{e2i[t]}" for h, r, t in triples
    ]
    return _tsv(rows, "triples_encoded.tsv")


@router.get("/entities.tsv", summary="Entités enrichies (features ML)")
async def export_entities() -> Response:
    """
    TSV des entités avec toutes les features utiles à un modèle :
    id, label, primary_type, type_count, out_degree, in_degree,
    total_degree, hub_score (out/total), authority_score (in/total), comment

    hub_score proche de 1   → nœud très émetteur (source, catégorie parente)
    authority_score proche de 1 → nœud très récepteur (concept cible, feuille)
    """
    e2i, _, triples, entity_meta, _ = _build_rich_index()

    # Degrés réels calculés depuis les triplets
    out_deg: Dict[str, int] = defaultdict(int)
    in_deg:  Dict[str, int] = defaultdict(int)
    for h, _, t in triples:
        out_deg[h] += 1
        in_deg[t]  += 1

    rows = ["id\tlabel\tprimary_type\ttype_count\tout_degree\tin_degree\ttotal_degree\thub_score\tauthority_score\tcomment"]
    for uri, idx in sorted(e2i.items(), key=lambda x: x[1]):
        meta = entity_meta.get(uri, {})
        out = out_deg.get(uri, 0)
        inp = in_deg.get(uri, 0)
        total = out + inp
        hub   = round(out / total, 4) if total else 0.0
        auth  = round(inp / total, 4) if total else 0.0
        types = meta.get("types", [])
        rows.append(
            f"{idx}\t{meta.get('label', _short(uri))}\t"
            f"{types[0] if types else ''}\t{meta.get('type_count', 0)}\t"
            f"{out}\t{inp}\t{total}\t{hub}\t{auth}\t"
            f"{meta.get('comment', '').replace(chr(9), ' ').replace(chr(10), ' ')}"
        )
    return _tsv(rows, "entities.tsv")


@router.get("/relations.tsv", summary="Relations enrichies avec métadonnées sémantiques")
async def export_relations() -> Response:
    """
    TSV des relations avec :
    id, label, usage (fréquence absolue), domains, ranges,
    symmetric, transitive, functional

    Utile pour pondérer les relations dans un embedding ou filtrer par type.
    """
    e2i, r2i, _, _, rel_meta = _build_rich_index()
    rows = ["id\tlabel\tusage\tdomains\tranges\tsymmetric\ttransitive\tfunctional"]
    for uri, idx in sorted(r2i.items(), key=lambda x: x[1]):
        meta = rel_meta.get(uri, {})
        rows.append(
            f"{idx}\t{meta.get('label', _short(uri))}\t"
            f"{meta.get('usage', 0)}\t"
            f"{','.join(meta.get('domains', []))}\t"
            f"{','.join(meta.get('ranges', []))}\t"
            f"{int(meta.get('symmetric', False))}\t"
            f"{int(meta.get('transitive', False))}\t"
            f"{int(meta.get('functional', False))}"
        )
    return _tsv(rows, "relations.tsv")


@router.get("/paths2.tsv", summary="Chemins longueur-2 (contexte de voisinage)")
async def export_paths2() -> Response:
    """
    TSV des chemins de longueur 2 : s -p1-> mid -p2-> o
    Colonnes : head_id  rel1_id  mid_id  rel2_id  tail_id

    Utilisé pour :
    - TransE-path, RotatE contextuel
    - Génération de features de voisinage (GNN, R-GCN)
    - Détection de règles d'inférence (PRA, AMIE)
    """
    e2i, r2i, base_triples, _, _ = _build_rich_index()

    # Construit l'index de voisinage depuis les triplets existants
    out_index: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for h, p, t in base_triples:
        out_index[h].append((p, t))

    rows = ["head_id\trel1_id\tmid_id\trel2_id\ttail_id"]
    seen: set = set()
    for h, p1, mid in base_triples:
        for p2, t in out_index.get(mid, []):
            if t == h:  # évite les cycles triviaux
                continue
            key = (h, p1, mid, p2, t)
            if key in seen:
                continue
            seen.add(key)
            if h in e2i and mid in e2i and t in e2i and p1 in r2i and p2 in r2i:
                rows.append(f"{e2i[h]}\t{r2i[p1]}\t{e2i[mid]}\t{r2i[p2]}\t{e2i[t]}")

    return _tsv(rows, "paths2.tsv")


@router.get("/literals.tsv", summary="Attributs littéraux des entités (features textuelles/numériques)")
async def export_literals() -> Response:
    """
    TSV des attributs non-relationnels (strings, nombres, dates).
    Colonnes : entity_id  predicate_id  value  datatype

    Utile pour :
    - Modèles mixtes (EARL, KGE + attributs)
    - Encodage de features initiales pour GNN
    - Filtrage/segmentation des entités
    """
    e2i, r2i, _, _, _ = _build_rich_index()

    rows = ["entity_id\tpredicate_id\tvalue\tdatatype"]
    for b in _run(_Q_LITERALS):
        uri = b["s"]["value"]
        pred = b["p"]["value"]
        if uri not in e2i:
            continue
        if pred not in r2i:
            r2i[pred] = len(r2i)
        val = b["val"]["value"].replace("\t", " ").replace("\n", " ")
        dt  = _short(b.get("dt", {}).get("value", "")) if b.get("dt") else "string"
        rows.append(f"{e2i[uri]}\t{r2i[pred]}\t{val}\t{dt}")

    return _tsv(rows, "literals.tsv")


@router.get("/negatives.tsv", summary="Triplets positifs + négatifs CWA")
async def export_negatives(
    seed:      Optional[int] = Query(None, description="Graine aléatoire"),
    neg_ratio: int           = Query(1, ge=1, le=10, description="Négatifs par positif"),
    strategy:  str           = Query("both", regex="^(head|tail|both)$"),
) -> Response:
    """
    Génère des négatifs par corruption CWA.
    Colonnes : head_id  rel_id  tail_id  label  corrupt_side

    corrupt_side (h/t) permet d'entraîner des modèles asymétriques
    ou de distinguer les erreurs de sujet vs objet.
    """
    rng = random.Random(seed)
    e2i, r2i, triples, _, _ = _build_rich_index()
    entities = list(e2i.keys())

    rows = ["head_id\trel_id\ttail_id\tlabel\tcorrupt_side"]
    for h, r, t in triples:
        rows.append(f"{e2i[h]}\t{r2i[r]}\t{e2i[t]}\t1\t-")
        for i in range(neg_ratio):
            corrupt_head = {"head": True, "tail": False, "both": i % 2 == 0}[strategy]
            for _ in range(20):
                c = rng.choice(entities)
                if corrupt_head and c != h:
                    rows.append(f"{e2i[c]}\t{r2i[r]}\t{e2i[t]}\t0\th")
                    break
                if not corrupt_head and c != t:
                    rows.append(f"{e2i[h]}\t{r2i[r]}\t{e2i[c]}\t0\tt")
                    break

    return _tsv(rows, "negatives.tsv")


@router.get("/mapping.json", summary="Dictionnaires entity2id / relation2id")
async def export_mapping() -> Response:
    """
    JSON de référence : mappings entier ↔ URI + ↔ label court.
    Indispensable pour interpréter les fichiers .tsv encodés.
    """
    e2i, r2i, triples, entity_meta, rel_meta = _build_rich_index()

    out_deg: Dict[str, int] = defaultdict(int)
    in_deg:  Dict[str, int] = defaultdict(int)
    for h, _, t in triples:
        out_deg[h] += 1
        in_deg[t]  += 1

    entities = {}
    for uri, idx in e2i.items():
        meta = entity_meta.get(uri, {})
        entities[str(idx)] = {
            "uri":        uri,
            "label":      meta.get("label", _short(uri)),
            "types":      meta.get("types", []),
            "out_degree": out_deg.get(uri, 0),
            "in_degree":  in_deg.get(uri, 0),
        }

    relations = {}
    for uri, idx in r2i.items():
        meta = rel_meta.get(uri, {})
        relations[str(idx)] = {
            "uri":        uri,
            "label":      meta.get("label", _short(uri)),
            "usage":      meta.get("usage", 0),
            "symmetric":  meta.get("symmetric", False),
            "transitive": meta.get("transitive", False),
            "functional": meta.get("functional", False),
        }

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "num_entities":  len(e2i),
            "num_relations": len(r2i),
            "num_triples":   len(triples),
        },
        "entities":  entities,
        "relations": relations,
    }
    return _json_resp(payload, "mapping.json")


@router.get("/stats.json", summary="Statistiques descriptives du KG")
async def export_stats() -> Response:
    """
    Métriques essentielles avant tout entraînement :
    densité, degrés, fréquences, type coverage.
    """
    e2i, r2i, triples, entity_meta, rel_meta = _build_rich_index()

    out_deg: Dict[str, int] = defaultdict(int)
    in_deg:  Dict[str, int] = defaultdict(int)
    rel_freq: Dict[str, int] = defaultdict(int)
    for h, r, t in triples:
        out_deg[h] += 1
        in_deg[t]  += 1
        rel_freq[r] += 1

    n, m = len(e2i), len(triples)
    density = round(m / (n * (n - 1)), 6) if n > 1 else 0.0

    deg_values = [out_deg[u] + in_deg[u] for u in e2i]
    deg_values.sort()
    p50 = deg_values[len(deg_values) // 2] if deg_values else 0
    p95 = deg_values[int(len(deg_values) * 0.95)] if deg_values else 0

    # Couverture des types
    typed   = sum(1 for m in entity_meta.values() if m.get("types"))
    labeled = sum(1 for m in entity_meta.values() if m.get("label") and m["label"] != _short(m.get("label", "")))

    return {
        "graph": {
            "num_entities":  n,
            "num_relations": len(r2i),
            "num_triples":   m,
            "density":       density,
        },
        "degrees": {
            "avg_total":   round(sum(deg_values) / n, 4) if n else 0,
            "median":      p50,
            "p95":         p95,
            "max_out":     max(out_deg.values(), default=0),
            "max_in":      max(in_deg.values(), default=0),
        },
        "coverage": {
            "typed_entities":   typed,
            "typed_pct":        round(typed / n * 100, 1) if n else 0,
            "labeled_entities": labeled,
        },
        "relation_frequency": {
            _short(r): cnt
            for r, cnt in sorted(rel_freq.items(), key=lambda x: -x[1])
        },
        "type_distribution": {
            t: sum(1 for m in entity_meta.values() if t in m.get("types", []))
            for t in {t for m in entity_meta.values() for t in m.get("types", [])}
        },
    }


@router.get("/type_cooccurrence.json", summary="Cooccurrences de types (signal de similarité)")
async def export_type_cooc() -> Response:
    """
    Pour chaque type : liste des entités membres.
    Permet de construire des paires positives (même type = similarité structurelle)
    et des paires négatives (types distincts) pour l'apprentissage contrastif.
    """
    data: Dict[str, Dict] = {}
    for b in _run(_Q_COOC):
        t   = b["type"]["value"]
        members = [_short(m) for m in b["members"]["value"].split("|") if m]
        data[_short(t)] = {
            "uri":    t,
            "count":  int(b["count"]["value"]),
            "members": members,
        }
    return _json_resp({"types": data}, "type_cooccurrence.json")


# ─────────────────────────────────────────────────────────────────────────────
# Graph exports (visualisation / import Gephi / NetworkX)
# ─────────────────────────────────────────────────────────────────────────────

@router_g.get("/nodes.csv", summary="Nœuds enrichis pour Gephi / NetworkX")
async def export_nodes_csv() -> Response:
    """
    CSV nœuds : id, label, primary_type, type_count,
                out_degree, in_degree, hub_score, authority_score
    """
    e2i, _, triples, entity_meta, _ = _build_rich_index()
    out_deg: Dict[str, int] = defaultdict(int)
    in_deg:  Dict[str, int] = defaultdict(int)
    for h, _, t in triples:
        out_deg[h] += 1
        in_deg[t]  += 1

    buf = io.StringIO()
    w   = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["id", "label", "primary_type", "type_count",
                "out_degree", "in_degree", "hub_score", "authority_score"])

    for uri in sorted(e2i):
        meta  = entity_meta.get(uri, {})
        out   = out_deg.get(uri, 0)
        inp   = in_deg.get(uri, 0)
        total = out + inp
        hub   = round(out / total, 4) if total else 0.0
        auth  = round(inp / total, 4) if total else 0.0
        types = meta.get("types", [])
        w.writerow([
            uri,
            meta.get("label", _short(uri)),
            types[0] if types else "",
            len(types),
            out, inp, hub, auth,
        ])
    return _csv_resp(buf, "nodes.csv", len(e2i))


@router_g.get("/edges.csv", summary="Arêtes avec poids et métadonnées")
async def export_edges_csv() -> Response:
    """
    CSV arêtes : source, target, relation, weight (usage normalisé 0-1),
                 symmetric, transitive
    """
    _, r2i, triples, _, rel_meta = _build_rich_index()

    max_usage = max((rel_meta.get(r, {}).get("usage", 1) for _, r, _ in triples), default=1)

    buf = io.StringIO()
    w   = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(["source", "target", "relation", "weight", "symmetric", "transitive"])

    for h, p, t in triples:
        meta   = rel_meta.get(p, {})
        weight = round(meta.get("usage", 1) / max_usage, 6)
        w.writerow([
            _short(h), _short(t), _short(p), weight,
            int(meta.get("symmetric", False)),
            int(meta.get("transitive", False)),
        ])
    return _csv_resp(buf, "edges.csv", len(triples))


@router_g.get("/graphml", summary="GraphML avec attributs sémantiques")
async def export_graphml() -> Response:
    """
    GraphML compatible Gephi / yEd / NetworkX.
    Attributs nœuds : label, primary_type, out_degree, in_degree, hub_score
    Attributs arêtes : label, usage, symmetric
    """
    e2i, _, triples, entity_meta, rel_meta = _build_rich_index()
    out_deg: Dict[str, int] = defaultdict(int)
    in_deg:  Dict[str, int] = defaultdict(int)
    for h, _, t in triples:
        out_deg[h] += 1
        in_deg[t]  += 1

    NS = "http://graphml.graphdrawing.org/graphml"
    root = ET.Element("graphml", {
        "xmlns": NS,
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": f"{NS} {NS}/1.0/graphml.xsd",
    })

    for kid, for_, name, atype in [
        ("nLabel",    "node", "label",        "string"),
        ("nType",     "node", "primary_type",  "string"),
        ("nOutDeg",   "node", "out_degree",    "int"),
        ("nInDeg",    "node", "in_degree",     "int"),
        ("nHub",      "node", "hub_score",     "double"),
        ("eLabel",    "edge", "label",         "string"),
        ("eUsage",    "edge", "usage",         "int"),
        ("eSymm",     "edge", "symmetric",     "boolean"),
    ]:
        ET.SubElement(root, "key", id=kid, **{"for": for_, "attr.name": name, "attr.type": atype})

    graph_el = ET.SubElement(root, "graph", id="G", edgedefault="directed")

    for uri in sorted(e2i):
        meta  = entity_meta.get(uri, {})
        out   = out_deg.get(uri, 0)
        inp   = in_deg.get(uri, 0)
        total = out + inp
        hub   = round(out / total, 4) if total else 0.0
        types = meta.get("types", [])
        n = ET.SubElement(graph_el, "node", id=uri)
        for k, v in [
            ("nLabel",  meta.get("label", _short(uri))),
            ("nType",   types[0] if types else ""),
            ("nOutDeg", str(out)),
            ("nInDeg",  str(inp)),
            ("nHub",    str(hub)),
        ]:
            ET.SubElement(n, "data", key=k).text = v

    for idx, (h, p, t) in enumerate(triples):
        meta = rel_meta.get(p, {})
        e = ET.SubElement(graph_el, "edge", id=f"e{idx}", source=h, target=t)
        for k, v in [
            ("eLabel",  meta.get("label", _short(p))),
            ("eUsage",  str(meta.get("usage", 0))),
            ("eSymm",   str(meta.get("symmetric", False)).lower()),
        ]:
            ET.SubElement(e, "data", key=k).text = v

    ET.indent(root, space="  ")
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return Response(
        xml_str.encode("utf-8"),
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="graph.graphml"'},
    )