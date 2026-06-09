"""
Peuplement automatique en cascade S-P-O (compatible explorateur triplet).
"""
from __future__ import annotations

import random
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .fuseki import fuseki_client

BASE_URI = "https://lms.flipova.fr/nsxai/v1/ontologies/data#"
GENERATED_PREFIX = "Generated"

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
OWL_CLASS = "http://www.w3.org/2002/07/owl#Class"
OWL_NI = "http://www.w3.org/2002/07/owl#NamedIndividual"
OWL_OP = "http://www.w3.org/2002/07/owl#ObjectProperty"
OWL_DP = "http://www.w3.org/2002/07/owl#DatatypeProperty"

SKIP_TYPES = {
    OWL_CLASS,
    OWL_NI,
    OWL_OP,
    OWL_DP,
    "http://www.w3.org/2002/07/owl#AnnotationProperty",
    "http://www.w3.org/2002/07/owl#Ontology",
    "http://www.w3.org/2002/07/owl#Thing",
}


def _is_datatype_range(range_uri: Optional[str]) -> bool:
    if not range_uri:
        return True
    low = range_uri.lower()
    return any(
        x in low
        for x in ("xmlschema", "literal", "string", "integer", "float", "boolean", "date")
    )


def _local_name(uri: str) -> str:
    return uri.split("#")[-1].split("/")[-1]


def _generated_uri(suffix: str) -> str:
    """URI locale préfixée Generated_* (repérable dans l'explorateur)."""
    safe = suffix.replace(" ", "_")
    return f"{BASE_URI}{GENERATED_PREFIX}_{safe}"


def _generated_label(kind: str, detail: str = "") -> str:
    base = f"{GENERATED_PREFIX} {kind}"
    return f"{base} {detail}".strip() if detail else base


def _load_schema() -> Tuple[List[str], Dict[str, List[dict]], List[dict]]:
    classes_q = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?class WHERE {
            ?class a owl:Class .
            FILTER(isIRI(?class))
        }
    """
    classes_r = fuseki_client.query(classes_q)
    classes = [
        b["class"]["value"]
        for b in classes_r["results"]["bindings"]
        if b["class"]["value"] not in SKIP_TYPES
    ]

    props_q = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl:  <http://www.w3.org/2002/07/owl#>
        PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT DISTINCT ?prop ?domain ?range ?kind WHERE {
            ?prop rdf:type ?kind .
            FILTER(?kind IN (owl:ObjectProperty, owl:DatatypeProperty))
            OPTIONAL { ?prop rdfs:domain ?domain }
            OPTIONAL { ?prop rdfs:range ?range }
        }
    """
    props_r = fuseki_client.query(props_q)
    by_domain: Dict[str, List[dict]] = {}
    generic: List[dict] = []

    for b in props_r["results"]["bindings"]:
        prop = {
            "uri": b["prop"]["value"],
            "domain": b.get("domain", {}).get("value"),
            "range": b.get("range", {}).get("value"),
            "isLiteral": _is_datatype_range(b.get("range", {}).get("value")),
        }
        d = prop["domain"]
        if d:
            by_domain.setdefault(d, []).append(prop)
        else:
            generic.append(prop)

    return classes, by_domain, generic


def _triples_for_resource(
    uri: str,
    types: List[str],
    label: str,
) -> List[Tuple[str, str, str, bool]]:
    rows: List[Tuple[str, str, str, bool]] = []
    for t in types:
        rows.append((uri, RDF_TYPE, t, False))
    if label:
        rows.append((uri, RDFS_LABEL, label, True))
    return rows


def populate_triplet_cascade(
    count: int = 50,
    chain_depth: int = 2,
    reuse_probability: float = 0.35,
) -> Dict[str, Any]:
    """
    Crée des racines typées puis enchaîne des triplets S-P-O selon domain/range.
    """
    classes, props_by_domain, generic_props = _load_schema()
    if not classes:
        return {"success": False, "error": "Aucune classe OWL dans le graphe", "count": 0}

    pool: Dict[str, List[str]] = {c: [] for c in classes}
    all_rows: List[Tuple[str, str, str, bool]] = []
    root_uris: List[str] = []

    def ensure_instance(class_uri: str, role: str = "Node") -> str:
        if class_uri in pool and pool[class_uri] and random.random() < reuse_probability:
            return random.choice(pool[class_uri])
        uid = str(uuid.uuid4())[:8]
        uri = _generated_uri(f"{role}_{_local_name(class_uri)}_{uid}")
        label = _generated_label(role, f"{_local_name(class_uri)} {uid[:4]}")
        types = [class_uri]
        if class_uri not in (OWL_CLASS, OWL_OP, OWL_DP):
            types.append(OWL_NI)
        rows = _triples_for_resource(uri, types, label)
        all_rows.extend(rows)
        pool.setdefault(class_uri, []).append(uri)
        return uri

    for i in range(count):
        cls = random.choice(classes)
        uid = str(uuid.uuid4())[:8]
        root = _generated_uri(f"Root_{_local_name(cls)}_{uid}")
        root_label = _generated_label("Root", f"{_local_name(cls)} #{i + 1}")
        root_types = [cls, OWL_NI]
        all_rows.extend(_triples_for_resource(root, root_types, root_label))
        pool.setdefault(cls, []).append(root)
        root_uris.append(root)

        current = root
        current_types = {cls}

        for _ in range(max(0, chain_depth)):
            candidates: List[dict] = []
            for t in current_types:
                candidates.extend(props_by_domain.get(t, []))
            candidates.extend(generic_props)
            if not candidates:
                break

            prop = random.choice(candidates)
            if prop["isLiteral"]:
                val = f"{GENERATED_PREFIX}_{uuid.uuid4().hex[:8]}"
                all_rows.append((current, prop["uri"], val, True))
                continue

            range_uri = prop.get("range")
            if range_uri and range_uri not in SKIP_TYPES and not _is_datatype_range(range_uri):
                target_class = range_uri
            else:
                target_class = random.choice(classes)

            target = ensure_instance(target_class, role="Node")
            all_rows.append((current, prop["uri"], target, False))

            current = target
            current_types = {target_class}

    sparql_parts = ["INSERT DATA {"]
    inserted_api = []
    for s, p, o, is_lit in all_rows:
        if is_lit:
            o_esc = o.replace("\\", "\\\\").replace('"', '\\"')
            sparql_parts.append(f'  <{s}> <{p}> "{o_esc}" .')
        else:
            sparql_parts.append(f"  <{s}> <{p}> <{o}> .")
        inserted_api.append({"s": s, "p": p, "o": o, "isLiteral": is_lit})
    sparql_parts.append("}")

    fuseki_client.update("\n".join(sparql_parts))

    return {
        "success": True,
        "count": count,
        "chainDepth": chain_depth,
        "triplesInserted": len(inserted_api),
        "roots": root_uris,
        "triples": inserted_api[:200],
    }
