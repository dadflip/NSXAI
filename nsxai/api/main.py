"""
NSXAI API - Point d'entrée FastAPI
Backend Python unifié pour le projet NSXAI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from .config import config
from .routes import sparql

# Création de l'application FastAPI
app = FastAPI(
    title="NSXAI API",
    description="Backend Python pour NSXAI - Semantic Analysis & Knowledge Graphs",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routes
app.include_router(sparql.router)

# Import des autres routes
from .routes import ontology, export, shacl, reasoner, predict
app.include_router(ontology.router)
app.include_router(export.router)
app.include_router(export.router_g)
app.include_router(shacl.router)
app.include_router(reasoner.router)
app.include_router(predict.router)


@app.get("/")
async def root():
    """Page d'accueil de l'API"""
    return {
        "name": "NSXAI API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "endpoints": {
            "sparql": "/api/sparql",
            "stats": "/api/sparql/stats",
            "ping": "/api/sparql/ping"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    from .services.fuseki import fuseki_client
    
    fuseki_alive = fuseki_client.ping()
    
    return {
        "status": "healthy" if fuseki_alive else "degraded",
        "fuseki": "connected" if fuseki_alive else "disconnected"
    }


@app.on_event("startup")
async def startup_event():
    """Actions au démarrage de l'API"""
    print("=" * 60)
    print("  NSXAI API - Demarrage")
    print("=" * 60)
    print(f"  Host: {config.api.host}:{config.api.port}")
    print(f"  Fuseki: {config.fuseki.url}")
    print(f"  Dataset: {config.fuseki.dataset}")
    print(f"  Docs: http://{config.api.host}:{config.api.port}/api/docs")
    print("=" * 60)
    
    # Vérifier la connexion à Fuseki
    from .services.fuseki import fuseki_client
    if fuseki_client.ping():
        print("[OK] Fuseki connecte")
        try:
            stats = fuseki_client.get_stats()
            print(f"  - Triplets: {stats['triples']}")
            print(f"  - Classes: {stats['classes']}")
            print(f"  - Proprietes: {stats['properties']}")
            print(f"  - Individus: {stats['individuals']}")
        except:
            pass
    else:
        print("[WARN] Fuseki non accessible - Demarrez Fuseki avec ./scripts/windows/start_fuseki.bat")
    print()


@app.on_event("shutdown")
async def shutdown_event():
    """Actions à l'arrêt de l'API"""
    print("\n[STOP] NSXAI API - Arret")


def main():
    """Point d'entrée pour lancer l'API"""
    uvicorn.run(
        "nsxai.api.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.debug,
        log_level="info"
    )


if __name__ == "__main__":
    main()
