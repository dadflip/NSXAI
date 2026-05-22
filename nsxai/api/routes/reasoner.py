"""
Routes Reasoner - Inference RDFS et gestion des regles
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List

from ..services.fuseki import fuseki_client

router = APIRouter(prefix="/api/reasoner", tags=["reasoner"])

DEFAULT_RULES: List[Dict[str, Any]] = [
    {
        'id': 'rdfs_domain',
        'name': 'RDFS Domain',
        'sparql': (
            'INSERT { ?s <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?D } '
            'WHERE { ?s ?p ?o . ?p <http://www.w3.org/2000/01/rdf-schema#domain> ?D . FILTER(isIRI(?s)) }'
        )
    },
    {
        'id': 'rdfs_range',
        'name': 'RDFS Range',
        'sparql': (
            'INSERT { ?o <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?R } '
            'WHERE { ?s ?p ?o . ?p <http://www.w3.org/2000/01/rdf-schema#range> ?R . FILTER(isIRI(?o)) }'
        )
    },
    {
        'id': 'rdfs_subclass_ind',
        'name': 'RDFS SubClass Instance Propagation',
        'sparql': (
            'INSERT { ?ind <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?superClass } '
            'WHERE { ?ind <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?subClass . '
            '?subClass <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?superClass . '
            'FILTER(isIRI(?ind) && isIRI(?superClass)) }'
        )
    },
    {
        'id': 'rdfs_subclass_trans',
        'name': 'RDFS SubClass Transitivity',
        'sparql': (
            'INSERT { ?sub <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?super } '
            'WHERE { ?sub <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?mid . '
            '?mid <http://www.w3.org/2000/01/rdf-schema#subClassOf> ?super . }'
        )
    }
]

_rules: List[Dict[str, Any]] = list(DEFAULT_RULES)
_inferred_triples: set = set()


def _run_rules(rules: List[Dict[str, Any]]) -> int:
    count_q = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"
    before = int(fuseki_client.query(count_q)['results']['bindings'][0]['count']['value'])

    prev_size, current_size, iterations = -1, before, 0
    while current_size != prev_size and iterations < 10:
        prev_size = current_size
        iterations += 1
        for rule in rules:
            try:
                fuseki_client.update(rule['sparql'])
            except Exception as e:
                print(f"[WARN] Rule {rule['id']} failed: {e}")
        current_size = int(fuseki_client.query(count_q)['results']['bindings'][0]['count']['value'])

    return max(current_size - before, 0)


@router.get("/rules")
async def get_rules() -> List[Dict[str, Any]]:
    return _rules


@router.post("/rules")
async def add_or_update_rule(request: Request) -> Dict[str, Any]:
    """Ajoute ou met a jour une regle (body: {id, name, sparql})"""
    global _rules
    body = await request.json()
    rule_id = body.get('id')
    if not rule_id or not body.get('sparql'):
        raise HTTPException(status_code=400, detail="Missing id or sparql")

    rule = {'id': rule_id, 'name': body.get('name', rule_id), 'sparql': body['sparql']}
    idx = next((i for i, r in enumerate(_rules) if r['id'] == rule_id), -1)
    if idx >= 0:
        _rules[idx] = rule
    else:
        _rules.append(rule)

    try:
        inferred = _run_rules(_rules)
        return {'success': True, 'inferred': inferred}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str) -> Dict[str, Any]:
    global _rules
    before = len(_rules)
    _rules = [r for r in _rules if r['id'] != rule_id]
    if len(_rules) == before:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {'success': True}


@router.post("/rules/sync")
async def sync_rules(request: Request) -> Dict[str, Any]:
    """Synchronise les regles depuis le frontend"""
    global _rules
    body = await request.json()
    rules = body.get('rules', [])
    if rules:
        _rules = rules
    return {'success': True, 'count': len(_rules)}


@router.post("/run")
async def run_reasoner() -> Dict[str, Any]:
    try:
        inferred = _run_rules(_rules)
        return {'success': True, 'inferred': inferred}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_reasoner_stats() -> Dict[str, Any]:
    try:
        count_q = "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }"
        total = int(fuseki_client.query(count_q)['results']['bindings'][0]['count']['value'])
        return {
            'totalTriples': total,
            'inferredTriples': len(_inferred_triples),
            'rulesCount': len(_rules),
            'shaclSupport': True,
            'rules': [r['name'] for r in _rules]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inferences")
async def get_inferences() -> List[str]:
    return list(_inferred_triples)


@router.delete("/inferences")
async def clear_inferences() -> Dict[str, Any]:
    _inferred_triples.clear()
    return {'success': True}


@router.delete("/inferences/{triple}")
async def delete_inference(triple: str) -> Dict[str, Any]:
    if triple in _inferred_triples:
        _inferred_triples.discard(triple)
        return {'success': True}
    raise HTTPException(status_code=404, detail="Triple not found in inferences")
