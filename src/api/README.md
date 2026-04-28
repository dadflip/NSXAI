# API - Interface REST pour NSXAI

Ce dossier contient l'API REST exposant les services du framework NSXAI.

## Structure

```
api/
├── __init__.py
├── config.py                    # Configuration de l'API (pydantic)
├── auth/                        # Authentification et autorisation
│   └── __init__.py
├── endpoints/                   # Routes API RESTful
│   └── __init__.py
├── middleware/                  # Middleware (CORS, rate limiting, logging)
│   └── __init__.py
├── schemas/                     # Modèles Pydantic (validation)
│   └── __init__.py
├── core/                        # Logique métier API
│   └── __init__.py
├── deps/                        # Dépendances injectables (FastAPI)
│   └── __init__.py
└── tests/                       # Tests API (pytest)
    └── __init__.py
```

## Architecture

L'API est construite avec **FastAPI** et suit les principes REST.

### Endpoints principaux (prévus)

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/ontologies` | GET | Liste des ontologies |
| `/api/v1/infer` | POST | Inférence symbolique |
| `/api/v1/predict` | POST | Prédiction neuro-symbolique |
| `/api/v1/explain` | POST | Explication hybride |

## Démarrage

```bash
# Installation des dépendances API
pip install -e ".[api]"

# Lancement de l'API
uvicorn api.main:app --reload
```

## Documentation interactive

Une fois lancée, la documentation est disponible :
- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`
