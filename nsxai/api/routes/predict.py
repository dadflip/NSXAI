from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from ..services.ml_service import ml_service

router = APIRouter(prefix="/api/predict", tags=["predict"])

class RecommendRequest(BaseModel):
    source_uri: str
    top_k: int = 5

class RecommendationResponse(BaseModel):
    target_uri: str
    probability: float

class PredictResponse(BaseModel):
    recommendations: List[RecommendationResponse]

@router.post("/recommendations", response_model=PredictResponse)
async def get_recommendations(req: RecommendRequest):
    """
    Retourne les recommandations ML pour une entité source donnée.
    """
    if not ml_service.is_loaded:
        # Essayer de synchroniser le graphe (et potentiellement charger le modèle s'il vient d'être déposé)
        ml_service.load_model()
        ml_service.sync_graph()
        
    if not ml_service.is_loaded:
        raise HTTPException(status_code=503, detail="Le modèle ML n'est pas chargé ou n'est pas disponible (model/weights/).")
        
    try:
        # Assurons-nous que le graphe est à jour pour les heuristiques
        # Idéalement, la synchronisation devrait être asynchrone / déclenchée sur mutation.
        # Pour le moment, on le fait à l'inférence ou si absent.
        if ml_service.G_mp is None:
            ml_service.sync_graph()
            
        recs = ml_service.predict_targets(req.source_uri, req.top_k)
        return PredictResponse(recommendations=recs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync")
async def sync_ml_graph(background_tasks: BackgroundTasks):
    """
    Déclenche manuellement la synchronisation du graphe ML depuis Fuseki.
    """
    background_tasks.add_task(ml_service.sync_graph)
    return {"status": "Sync initiated"}

@router.get("/status")
async def get_ml_status():
    """
    Retourne le statut actuel du service ML (modèle chargé, graphe synchronisé).
    """
    # On essaie de charger le modèle si on ne l'a pas encore fait
    if not ml_service.is_loaded:
        ml_service.load_model()
        
    expected_dim = None
    if ml_service.is_loaded and ml_service.model is not None:
        if hasattr(ml_service.model, "n_features_in_"):
            expected_dim = ml_service.model.n_features_in_
        elif hasattr(ml_service.model, "num_features"):
            expected_dim = ml_service.model.num_features()

    return {
        "status": "ready" if ml_service.is_loaded else "unavailable",
        "active_model": ml_service.active_model_name,
        "model_type": ml_service.model_type,
        "nodes_loaded": len(ml_service.node_to_idx) if ml_service.is_loaded else 0,
        "expected_features": expected_dim
    }

class SelectModelRequest(BaseModel):
    model_name: str

@router.post("/select-model")
async def select_model(req: SelectModelRequest, background_tasks: BackgroundTasks):
    """
    Change le modèle actif pour les prédictions en temps réel.
    """
    try:
        ml_service.set_active_model(req.model_name)
        if ml_service.is_loaded:
            # Resync graph features for the new model if needed
            if ml_service.G_mp is None:
                background_tasks.add_task(ml_service.sync_graph)
            else:
                ml_service.sync_graph()
            return {"status": "success", "active_model": req.model_name}
        else:
            raise HTTPException(status_code=404, detail=f"Modèle {req.model_name} introuvable ou échec de chargement.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import os
import json

@router.get("/training-results")
async def get_training_results():
    """
    Retourne les résultats d'entraînement ML stockés dans output_files/model_comparison.json
    ainsi que model_comparison_summary.csv s'ils existent.
    """
    base_dir = os.path.dirname(__file__)
    json_path = os.path.join(base_dir, "../../../model/output_files/model_comparison.json")
    
    if not os.path.exists(json_path):
        return {"status": "not_found", "data": []}
        
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {"status": "ok", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
