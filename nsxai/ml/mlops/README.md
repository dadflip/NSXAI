# Gamification Recommendation API

Neuro-symbolic REST API serving game element recommendations for Java topics.
Built on the output of the 5-layer pipeline (Task 1 → 4).

## Prerequisites

- Python 3.10+ **or** Docker + Docker Compose
- `task4_explanations.csv` produced by the notebook pipeline

---

## Quick start — Python

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy your pipeline output
cp /path/to/task4_explanations.csv ./artifacts/

# 3. Run
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## Quick start — Docker

```bash
# 1. Copy your pipeline output
cp /path/to/task4_explanations.csv ./artifacts/

# 2. Build & run
docker compose up --build

# Stop
docker compose down
```

The `artifacts/` folder is **mounted as a volume** — you can drop a new CSV
and restart without rebuilding the image.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check + counts |
| GET | `/topics` | All available Java topics |
| GET | `/elements` | All available game elements |
| GET | `/recommend/{topic}` | Top-K recommendations for a topic |
| POST | `/recommend/batch` | Recommendations for multiple topics |
| GET | `/element/{element}` | Which topics recommend this element |
| GET | `/stats` | Dataset summary statistics |

---

## Usage examples

### Single topic
```bash
curl "http://localhost:8000/recommend/Variables"
curl "http://localhost:8000/recommend/Variables?top_k=3"
curl "http://localhost:8000/recommend/Variables?only_novel=true"
curl "http://localhost:8000/recommend/Variables?min_score=0.6"
```

### Batch
```bash
curl -X POST "http://localhost:8000/recommend/batch" \
  -H "Content-Type: application/json" \
  -d '{"topics": ["Variables", "Loops", "Arrays"], "top_k": 3}'
```

### Reverse lookup
```bash
curl "http://localhost:8000/element/Level_Up"
```

---

## Response format

```json
{
  "topic": "Variables",
  "count": 5,
  "recommendations": [
    {
      "game_element":        "Level_Up",
      "neurosymbolic_score": 0.955,
      "neural_probability":  0.85,
      "symbolic_confidence": 1.0,
      "confidence_label":    "High",
      "path_distance":       1,
      "key_relation":        "containsGameElement",
      "ontology_path":       "Variables --containsGameElement--> Level_Up",
      "is_validated":        true,
      "explanation":         "Level_Up is strongly recommended for Variables..."
    }
  ]
}
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARTIFACTS_DIR` | `./artifacts` | Path to the folder containing `task4_explanations.csv` |

---

## Run tests

```bash
pytest tests/test_api.py -v
```

All 14 tests use a small mock CSV — no pipeline output needed to test.

---

## Refresh data after re-running the pipeline

```bash
cp /path/to/new/task4_explanations.csv ./artifacts/
docker compose restart      # or kill & restart uvicorn
```

The API re-reads the CSV at startup — no code change needed.
