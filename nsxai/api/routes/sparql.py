"""
Routes SPARQL - Proxy vers Fuseki
"""
import json
from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any

from ..services.fuseki import fuseki_client

router = APIRouter(prefix="/api", tags=["sparql"])


@router.post("/sparql")
async def execute_sparql(request: Request) -> Dict[str, Any]:
    """
    Execute une requete SPARQL SELECT/CONSTRUCT/ASK

    Accepte:
    - Content-Type: application/sparql-query  (corps = requete brute)
    - Content-Type: text/plain               (corps = requete brute)
    - Content-Type: application/json         ({"query": "..."})
    """
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    if "application/json" in content_type:
        data = json.loads(body)
        query = data.get("query", "")
    else:
        query = body.decode("utf-8")

    if not query.strip():
        raise HTTPException(status_code=400, detail="Missing SPARQL query")

    try:
        return fuseki_client.query(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sparql/update")
async def execute_sparql_update(request: Request) -> Dict[str, bool]:
    """
    Execute une requete SPARQL UPDATE (INSERT/DELETE/LOAD)

    Accepte:
    - Content-Type: application/sparql-update (corps = requete brute)
    - Content-Type: application/json          ({"update": "..."})
    """
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    if "application/json" in content_type:
        data = json.loads(body)
        update = data.get("update", "")
    else:
        update = body.decode("utf-8")

    if not update.strip():
        raise HTTPException(status_code=400, detail="Missing SPARQL update")

    try:
        success = fuseki_client.update(update)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sparql/stats")
async def get_dataset_stats() -> Dict[str, int]:
    """Statistiques du dataset (triples, classes, properties, individuals)"""
    try:
        return fuseki_client.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sparql/ping")
async def ping_fuseki() -> Dict[str, bool]:
    """Verifie que Fuseki est accessible"""
    if not fuseki_client.ping():
        raise HTTPException(status_code=503, detail="Fuseki is not accessible")
    return {"alive": True}
