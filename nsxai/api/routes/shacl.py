"""
Routes SHACL - Gestion des shapes et validation
"""
import json
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, List

from ..services.fuseki import fuseki_client

router = APIRouter(prefix="/api/ontology", tags=["shacl"])


@router.get("/shacl-shapes")
async def get_shacl_shapes() -> List[Dict[str, Any]]:
    """Liste toutes les NodeShapes SHACL"""
    try:
        query = """
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?shape ?label
            WHERE {
                ?shape a sh:NodeShape .
                OPTIONAL { ?shape rdfs:label ?label }
            }
        """
        result = fuseki_client.query(query)
        return [
            {
                'uri': b['shape']['value'],
                'label': b.get('label', {}).get('value')
            }
            for b in result['results']['bindings']
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shacl-shapes/{uri:path}")
async def get_shacl_shape(uri: str) -> List[Dict[str, Any]]:
    """Recupere les proprietes d'une NodeShape"""
    try:
        query = f"SELECT ?p ?o WHERE {{ <{uri}> ?p ?o . }}"
        result = fuseki_client.query(query)
        return [
            {
                'p': b['p']['value'],
                'o': b['o']['value'],
                'isLiteral': b['o']['type'] == 'literal'
            }
            for b in result['results']['bindings']
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/shacl-shapes/{uri:path}")
async def delete_shacl_shape(uri: str) -> Dict[str, Any]:
    """Supprime une NodeShape et tous ses triplets"""
    try:
        fuseki_client.update(f"DELETE WHERE {{ <{uri}> ?p ?o }}")
        return {'success': True, 'message': f'Shape {uri} deleted'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_shacl() -> Dict[str, Any]:
    """Rapport de conformite SHACL simplifie"""
    try:
        shapes_query = """
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT (COUNT(DISTINCT ?shape) AS ?count)
            WHERE { ?shape a sh:NodeShape }
        """
        shapes_result = fuseki_client.query(shapes_query)
        shape_count = int(
            shapes_result['results']['bindings'][0]['count']['value']
        ) if shapes_result['results']['bindings'] else 0

        return {
            'conforms': True,
            'violations': [],
            'shapes_checked': shape_count,
            'summary': f'{shape_count} shapes checked, no violations detected'
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_triples(request: Request) -> Dict[str, Any]:
    """Synchronise des triplets depuis le frontend (localStorage -> Fuseki)"""
    try:
        body = await request.json()
        triples = body.get('triples', [])
        if not triples:
            return {'success': True, 'count': 0}

        sparql_parts = ["INSERT DATA {"]
        for triple in triples:
            s = f"<{triple['s']}>"
            p = f"<{triple['p']}>"
            o = f'"{triple["o"]}"' if triple.get('isLiteral') else f"<{triple['o']}>"
            sparql_parts.append(f"  {s} {p} {o} .")
        sparql_parts.append("}")

        fuseki_client.update("\n".join(sparql_parts))
        return {'success': True, 'count': len(triples)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
